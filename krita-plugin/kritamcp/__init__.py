"""
Krita MCP Bridge - HTTP server for external paint commands in Krita
Allows Claude (or any MCP client) to paint by sending commands to this plugin.
"""

from krita import *
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QPointF, QRectF, Qt, QItemSelectionModel
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QMessageBox, QApplication, QTableView, QDockWidget
import json
import threading
import math
import functools
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import os
import sys
import uuid

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


@functools.lru_cache(maxsize=64)
def _make_stamp_mask(radius, hardness):
    """Precompute a circular brush-stamp alpha mask (0..1), cached by (radius, hardness).

    Unlike a boolean `dist <= radius` cutoff, this anti-aliases the outer rim over
    ~1px so stroke edges aren't stair-stepped, while still respecting `hardness`
    as the point at which the falloff begins (matches the previous behavior's
    intent, just smoothed).
    """
    r = max(radius, 1)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    dist = np.sqrt(xx.astype(np.float64) ** 2 + yy.astype(np.float64) ** 2)
    hardness = min(max(hardness, 0.0), 1.0)
    hard_r = hardness * r
    denom = max(r - hard_r, 1e-6)
    falloff = np.where(dist <= hard_r, 1.0, np.clip(1.0 - (dist - hard_r) / denom, 0.0, 1.0))
    # 1px anti-aliased rim right at the true circle edge.
    aa = np.clip(r + 0.5 - dist, 0.0, 1.0)
    return (falloff * aa).astype(np.float32)

# Logging utility - use stderr to avoid corrupting MCP stdio channel
def log(message, request_id=None):
    """Log to stderr to avoid polluting stdout."""
    prefix = f"[Krita Plugin]"
    if request_id:
        prefix = f"[Krita Plugin:{request_id[:8]}]"
    print(f"{prefix} {message}", file=sys.stderr, flush=True)

# Configuration - customize these as needed
SERVER_PORT = 5678
CANVAS_OUTPUT_DIR = os.path.expanduser("~/krita-mcp-output")

class CommandQueue:
    """Thread-safe command queue for passing commands from HTTP thread to main thread."""
    def __init__(self):
        self.queue = []
        self.results = {}
        self.lock = threading.Lock()
        self.result_event = threading.Event()

    def push(self, command_id, command):
        with self.lock:
            self.queue.append((command_id, command))

    def pop(self):
        with self.lock:
            if self.queue:
                return self.queue.pop(0)
            return None

    def set_result(self, command_id, result):
        with self.lock:
            self.results[command_id] = result
        self.result_event.set()

    def get_result(self, command_id, timeout=120):
        """Wait for result with timeout.

        The default timeout of 120s is important — canvas export and save
        operations can take a long time on large canvases. The original 30s
        default caused frequent timeouts. The MCP server's send_command()
        timeout must match or exceed this value.
        """
        start = threading.Event()
        for _ in range(int(timeout * 10)):  # Check every 100ms
            with self.lock:
                if command_id in self.results:
                    result = self.results.pop(command_id)
                    return result
            self.result_event.wait(0.1)
            self.result_event.clear()
        return {"error": "Timeout waiting for command execution"}

# Global command queue
command_queue = CommandQueue()
command_counter = 0


# =============================================================================
# STATE VERIFICATION FRAMEWORK (P0.1)
# =============================================================================

class StateVerifier:
    """Reusable state verification for Krita operations."""
    
    def __init__(self, request_id=None):
        self.request_id = request_id or str(uuid.uuid4())[:8]
    
    def log(self, message):
        log(message, self.request_id)
    
    def verify_document(self, doc, operation="operation"):
        if doc is None:
            self.log(f"{operation}: Document is None")
            return False, {"error_type": "DOCUMENT_NOT_FOUND", "message": "No active document", "recoverable": False, "request_id": self.request_id}
        try:
            _ = doc.width()
            _ = doc.height()
            return True, None
        except Exception as e:
            self.log(f"{operation}: Document invalid: {e}")
            return False, {"error_type": "DOCUMENT_INVALID", "message": f"Document not accessible: {e}", "recoverable": False, "request_id": self.request_id}
    
    def verify_layer_selected(self, doc, expected_layer, operation="select_layer"):
        try:
            actual_layer = doc.activeNode()
            if actual_layer is None:
                self.log(f"{operation}: Active layer is None")
                return False, None, {"error_type": "LAYER_SELECTION_FAILED", "message": "Layer selection failed", "recoverable": True, "request_id": self.request_id}
            if actual_layer != expected_layer:
                self.log(f"{operation}: Layer mismatch")
                return False, actual_layer, {"error_type": "LAYER_SELECTION_MISMATCH", "message": "Layer selection mismatch", "expected_layer": expected_layer.name(), "actual_layer": actual_layer.name(), "recoverable": True, "request_id": self.request_id}
            self.log(f"{operation}: Layer verified")
            return True, actual_layer, None
        except Exception as e:
            self.log(f"{operation}: Verification failed: {e}")
            return False, None, {"error_type": "LAYER_VERIFICATION_ERROR", "message": str(e), "recoverable": False, "request_id": self.request_id}
    
    def verify_frame_selected(self, doc, expected_frame, operation="set_frame"):
        try:
            actual_frame = int(doc.currentTime())
            if actual_frame != expected_frame:
                self.log(f"{operation}: Frame mismatch")
                return False, actual_frame, {"error_type": "FRAME_SELECTION_MISMATCH", "message": "Frame selection mismatch", "expected_frame": expected_frame, "actual_frame": actual_frame, "recoverable": True, "request_id": self.request_id}
            self.log(f"{operation}: Frame verified")
            return True, actual_frame, None
        except Exception as e:
            self.log(f"{operation}: Verification failed: {e}")
            return False, None, {"error_type": "FRAME_VERIFICATION_ERROR", "message": str(e), "recoverable": False, "request_id": self.request_id}
    
    def verify_keyframe_exists(self, node, doc, frame, operation="keyframe"):
        try:
            has_method = getattr(node, "hasKeyframeAtTime", None)
            if not callable(has_method):
                return False, False, None
            exists = bool(has_method(int(frame)))
            self.log(f"{operation}: Keyframe at {frame} exists={exists}")
            return True, exists, None
        except Exception as e:
            self.log(f"{operation}: Verification failed: {e}")
            return False, False, None
    
    def verify_file_created(self, filepath, min_size=100, operation="file"):
        import os
        try:
            if not os.path.exists(filepath):
                self.log(f"{operation}: File not created")
                return False, None, {"error_type": "FILE_NOT_CREATED", "message": f"File not created: {filepath}", "filepath": filepath, "recoverable": False, "request_id": self.request_id}
            file_size = os.stat(filepath).st_size
            if file_size < min_size:
                self.log(f"{operation}: File too small")
                return False, None, {"error_type": "FILE_TOO_SMALL", "message": f"File too small: {file_size} bytes", "filepath": filepath, "file_size": file_size, "recoverable": False, "request_id": self.request_id}
            self.log(f"{operation}: File verified ({file_size} bytes)")
            return True, {"filepath": filepath, "file_size": file_size}, None
        except Exception as e:
            self.log(f"{operation}: Verification failed: {e}")
            return False, None, {"error_type": "FILE_VERIFICATION_ERROR", "message": str(e), "filepath": filepath, "recoverable": False, "request_id": self.request_id}
    
    def verify_document_in_view(self, app, doc, operation="doc"):
        try:
            window = app.activeWindow()
            if not window:
                return False, {"error_type": "WINDOW_NOT_FOUND", "message": "No active window", "recoverable": False, "request_id": self.request_id}
            views = window.views()
            if not any(v.document() == doc for v in views):
                return False, {"error_type": "DOCUMENT_NOT_IN_VIEW", "message": "Document not in view", "recoverable": False, "request_id": self.request_id}
            self.log(f"{operation}: Document in view verified")
            return True, None
        except Exception as e:
            return False, {"error_type": "DOCUMENT_VIEW_VERIFICATION_ERROR", "message": str(e), "recoverable": False, "request_id": self.request_id}


class PaintRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for paint commands."""

    def log_message(self, format, *args):
        # Suppress HTTP logging
        pass

    def send_json_response(self, data, status=200):
        try:
            payload = json.dumps(data, default=str).encode()
        except (TypeError, ValueError) as e:
            payload = json.dumps({"error": f"Failed to encode response: {e}"}).encode()
            status = 500

        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        """Handle GET requests - mainly for health check."""
        parsed = urlparse(self.path)

        if parsed.path == '/health':
            self.send_json_response({"status": "ok", "plugin": "kritamcp"})
        elif parsed.path == '/info':
            self.send_json_response({
                "status": "ok",
                "canvas_dir": CANVAS_OUTPUT_DIR,
                "commands": [
                    "new_canvas", "set_color", "set_brush", "stroke",
                    "fill", "draw_shape", "get_canvas", "undo", "redo",
                    "draw_path",
                    "clear", "save", "get_color_at", "list_brushes",
                    "open_file", "select_paint_layer",
                    "create_frame", "select_frame", "get_current_frame",
                    "set_current_frame", "create_keyframe", "delete_keyframe", "list_keyframes", "has_keyframe",
                    "enable_onion", "inspect_previous_frame", "bulk_strokes",
                    "list_layers", "get_canvas_info", "draw_scene", "configure_animation"
                ]
            })
        else:
            self.send_json_response({"error": "Unknown endpoint"}, 404)

    def do_POST(self):
        """Handle POST requests - paint commands."""
        global command_counter

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            command = json.loads(body)
        except json.JSONDecodeError:
            self.send_json_response({"error": "Invalid JSON"}, 400)
            return

        # Assign command ID and queue it
        command_counter += 1
        command_id = command_counter
        command_queue.push(command_id, command)

        # Wait for result from main thread
        result = command_queue.get_result(command_id)

        if "error" in result:
            self.send_json_response(result, 500)
        else:
            self.send_json_response(result)


class ServerThread(QThread):
    """Thread to run HTTP server without blocking Krita UI."""

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.server = None

    def run(self):
        self.server = HTTPServer(('localhost', self.port), PaintRequestHandler)
        self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.shutdown()


class KritaMCPExtension(Extension):
    """Main Krita extension class."""

    def __init__(self, parent):
        super().__init__(parent)
        self.server_thread = None
        self.timer = None
        self.current_brush_size = 20
        self.current_opacity = 1.0

    def setup(self):
        """Called when extension is loaded."""
        pass

    def createActions(self, window):
        """Called when a new window is created."""
        # Ensure output directory exists
        os.makedirs(CANVAS_OUTPUT_DIR, exist_ok=True)

        # Start HTTP server
        if self.server_thread is None:
            self.server_thread = ServerThread(SERVER_PORT)
            self.server_thread.start()
            log(f"HTTP server started on port {SERVER_PORT}")

        # Start timer to process command queue
        if self.timer is None:
            self.timer = QTimer()
            self.timer.timeout.connect(self.process_commands)
            self.timer.start(50)  # Check every 50ms

    def process_commands(self):
        """Process commands from queue in main thread."""
        item = command_queue.pop()
        if item is None:
            return

        command_id, command = item
        result = self.execute_command(command)
        command_queue.set_result(command_id, result)

    def execute_command(self, command):
        """Execute a paint command and return result."""
        try:
            action = command.get("action")
            params = command.get("params", {})
            request_id = command.get("request_id", str(uuid.uuid4()))
            
            log(f"Executing: {action}", request_id)

            if action == "new_canvas":
                return self.cmd_new_canvas(params)
            elif action == "set_color":
                return self.cmd_set_color(params)
            elif action == "set_brush":
                return self.cmd_set_brush(params)
            elif action == "stroke":
                return self.cmd_stroke(params)
            elif action == "fill":
                return self.cmd_fill(params)
            elif action == "draw_shape":
                return self.cmd_draw_shape(params)
            elif action == "draw_path":
                return self.cmd_draw_path(params)
            elif action == "get_canvas":
                return self.cmd_get_canvas(params)
            elif action == "undo":
                return self.cmd_undo(params)
            elif action == "redo":
                return self.cmd_redo(params)
            elif action == "clear":
                return self.cmd_clear(params)
            elif action == "save":
                return self.cmd_save(params)
            elif action == "get_color_at":
                return self.cmd_get_color_at(params)
            elif action == "list_brushes":
                return self.cmd_list_brushes(params)
            elif action == "open_file":
                return self.cmd_open_file(params)
            elif action == "select_paint_layer":
                return self.cmd_select_paint_layer(params)
            elif action == "create_frame":
                return self.cmd_create_frame(params)
            elif action == "select_frame":
                return self.cmd_select_frame(params)
            elif action == "configure_animation":
                return self.cmd_configure_animation(params, request_id)
            elif action == "get_current_frame":
                return self.cmd_get_current_frame(params)
            elif action == "set_current_frame":
                return self.cmd_set_current_frame(params)
            elif action == "create_keyframe":
                return self.cmd_create_keyframe(params)
            elif action == "delete_keyframe":
                return self.cmd_delete_keyframe(params)
            elif action == "list_keyframes":
                return self.cmd_list_keyframes(params)
            elif action == "has_keyframe":
                return self.cmd_has_keyframe(params)
            elif action == "enable_onion":
                return self.cmd_enable_onion(params)
            elif action == "inspect_previous_frame":
                return self.cmd_inspect_previous_frame(params)
            elif action == "draw_scene":
                return self.cmd_draw_scene(params, request_id)
            elif action == "bulk_strokes":
                return self.cmd_bulk_strokes(params)
            elif action == "list_layers":
                return self.cmd_list_layers(params)
            elif action == "get_canvas_info":
                return self.cmd_get_canvas_info(params)
            else:
                return {"error": f"Unknown action: {action}", "request_id": request_id}

        except Exception as e:
            log(f"Exception in {action}: {e}", request_id)
            return {"error": str(e), "request_id": request_id}

    def get_active_document(self):
        """Get active document or return None."""
        app = Krita.instance()
        return app.activeDocument()

    def get_active_view(self):
        """Get active view or return None."""
        app = Krita.instance()
        window = app.activeWindow()
        if window:
            return window.activeView()
        return None

    def get_active_layer(self):
        """Get active paint layer."""
        doc = self.get_active_document()
        if doc:
            return doc.activeNode()
        return None

    def _find_first_paint_layer(self, node):
        """Depth-first search for the first paint layer node."""
        if not node:
            return None
        try:
            if node.type() == "paintlayer":
                return node
        except Exception:
            pass

        for child in node.childNodes() or []:
            found = self._find_first_paint_layer(child)
            if found:
                return found
        return None

    def _get_active_paint_layer(self):
        """Return active paint layer, falling back to first paint layer in the document."""
        doc = self.get_active_document()
        if not doc:
            return None

        node = doc.activeNode()
        try:
            if node and node.type() == "paintlayer":
                return node
        except Exception:
            pass

        return self._find_first_paint_layer(doc.rootNode())

    def _ensure_active_paint_layer(self):
        """Ensure a paint layer is selected as the active node."""
        doc = self.get_active_document()
        if not doc:
            return None

        layer = self._get_active_paint_layer()
        if layer:
            doc.setActiveNode(layer)
        return layer

    # --- Animation keyframe helpers (Krita 5.3+ real API) ---
    #
    # Keyframe creation is NOT exposed through the Python API in Krita 5.3.
    # The only way to create a real raster keyframe is to drive Krita's own
    # timeline machinery: the Animation Timeline docker is constructed at
    # startup (it is a QTableView), and its "add_blank_frame" / 
    # "add_duplicate_frame" / "remove_frames" actions are wired to the
    # timeline model. We find the frames view through the widget tree and use
    # plain QTableView/QAbstractItemModel calls (all wrapped by PyQt) to set
    # the selection, then trigger the action.

    def _get_current_time(self, doc):
        """Current playback position of the document."""
        return int(doc.currentTime())

    def _set_current_time(self, doc, frame):
        """Move the playhead to the given frame."""
        doc.setCurrentTime(int(frame))
        return int(doc.currentTime())

    def _ensure_node_animated(self, node):
        """Ensure the node has a raster keyframe channel enabled."""
        try:
            if node.animated():
                return
        except Exception:
            pass
        enable = getattr(node, "enableAnimation", None)
        if callable(enable):
            try:
                enable()
            except Exception:
                pass

    def _timeline_view(self):
        """Find the Animation Timeline frames view (a QTableView).

        Krita constructs every docker at startup and the docker is a child of
        each main window, so this works even when the docker is hidden. A view
        connected to a document (model with rows) is preferred.
        """
        best = None
        for widget in QApplication.topLevelWidgets():
            dock = widget.findChild(QDockWidget, "TimelineDocker")
            if not dock:
                continue
            view = dock.widget()
            if not isinstance(view, QTableView):
                view = dock.findChild(QTableView)
            if not view:
                continue
            model = view.model()
            if model is not None and model.rowCount() > 0:
                return view
            if best is None:
                best = view
        return best

    def _active_layer_row(self, view):
        """Row of the active layer in the timeline model.

        Primary: match the row's display name (column 0) to the active paint
        layer's name. Fallback: the plugin-internal ActiveLayerRole, detected
        numerically (it is the only role that yields True for exactly one row).
        """
        model = view.model()
        if model is None:
            return None
        node = self._get_active_paint_layer()
        if node is not None:
            try:
                name = node.name()
                for r in range(model.rowCount()):
                    try:
                        if str(model.data(model.index(r, 0))) == name:
                            return r
                    except Exception:
                        pass
            except Exception:
                pass
        rows = model.rowCount()
        for role in range(Qt.UserRole, Qt.UserRole + 80):
            hits = []
            for r in range(rows):
                try:
                    value = model.data(model.index(r, 0), role)
                except Exception:
                    value = None
                if isinstance(value, bool) and value:
                    hits.append(r)
            if len(hits) == 1:
                return hits[0]
        return None

    def _select_timeline_cell(self, view, row, frame):
        """Select cell (row, frame) in the timeline and make it current."""
        model = view.model()
        if model is None:
            return False
        frame = int(frame)
        try:
            if frame < 0 or frame >= model.columnCount():
                return False
            index = model.index(row, frame)
            if not index.isValid():
                return False
        except Exception:
            return False
        view.setCurrentIndex(index)
        view.selectionModel().select(
            index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Current)
        return True

    def _trigger_animation_action(self, name):
        """Trigger a Krita timeline action, bypassing its enabled state."""
        action = Krita.instance().action(name)
        if action is None:
            return False
        if action.isEnabled():
            action.trigger()
        else:
            action.triggered.emit()
        return True

    def _clear_frame_content(self, node, doc):
        """Erase the current frame's content (transparent)."""
        try:
            w = doc.width()
            h = doc.height()
            node.setPixelData(bytes([0, 0, 0, 0]) * (w * h), 0, 0, w, h)
            doc.refreshProjection()
            return True
        except Exception:
            return False

    def _create_keyframe(self, node, doc, frame):
        """Create a REAL raster keyframe at `frame` on `node`.

        Primary path: select the cell and trigger "add_blank_frame" (a true
        blank keyframe). Fallback: "add_duplicate_frame" then erase the
        copied content to blank.
        """
        frame = int(frame)
        if frame < 0:
            frame = 0
        self._ensure_node_animated(node)

        # Move the playhead first; the timeline model expands to cover it.
        self._set_current_time(doc, frame)
        QApplication.processEvents()

        if self._has_keyframe(node, doc, frame):
            return True

        view = self._timeline_view()
        if view is None:
            return self._has_keyframe(node, doc, frame)

        row = self._active_layer_row(view)
        if row is not None and not self._select_timeline_cell(view, row, frame):
            # The model may not have expanded to cover `frame` yet.
            QApplication.processEvents()
            QApplication.processEvents()
            if not self._select_timeline_cell(view, row, frame):
                return self._has_keyframe(node, doc, frame)
        if row is None:
            return self._has_keyframe(node, doc, frame)

        # Primary: insert a blank keyframe (what the "New Frame" button
        # in the Animation Timeline docker does).
        self._trigger_animation_action("add_blank_frame")
        QApplication.processEvents()
        if self._has_keyframe(node, doc, frame):
            return True

        # Fallback: duplicate the current frame, then erase it to blank.
        self._trigger_animation_action("add_duplicate_frame")
        QApplication.processEvents()
        if self._has_keyframe(node, doc, frame):
            self._clear_frame_content(node, doc)
        return self._has_keyframe(node, doc, frame)

    def _delete_keyframe(self, node, doc, frame):
        """Delete the raster keyframe at `frame` on `node` via remove_frames."""
        frame = int(frame)
        if not self._has_keyframe(node, doc, frame):
            return True
        view = self._timeline_view()
        if view is None:
            return False
        row = self._active_layer_row(view)
        if row is None or not self._select_timeline_cell(view, row, frame):
            return False
        QApplication.processEvents()
        self._trigger_animation_action("remove_frames")
        QApplication.processEvents()
        return not self._has_keyframe(node, doc, frame)

    def _list_keyframes(self, node, doc):
        return self._scan_keyframes_with_predicate(node, doc)

    def _scan_keyframes_with_predicate(self, node, doc):
        """Scan for keyframes using hasKeyframeAtTime (real 5.3 API)."""
        has_method = getattr(node, "hasKeyframeAtTime", None)
        if not callable(has_method):
            return []
        try:
            limit = max(32, int(doc.animationLength()) + 8, int(doc.currentTime()) + 64)
        except Exception:
            limit = 128
        output = []
        for t in range(0, limit + 1):
            try:
                if has_method(int(t)):
                    output.append(int(t))
            except Exception:
                break
        return sorted(set(output))

    def _has_keyframe(self, node, doc, frame):
        frame = int(frame)
        has_method = getattr(node, "hasKeyframeAtTime", None)
        if callable(has_method):
            try:
                return bool(has_method(frame))
            except Exception:
                pass
        return frame in self._list_keyframes(node, doc)

    def cmd_new_canvas(self, params, request_id=None):
        """P0.5: Create new canvas WITH VERIFICATION."""
        verifier = StateVerifier(request_id)
        width = params.get("width", 800)
        height = params.get("height", 600)
        name = params.get("name", "New Canvas")
        bg_color = params.get("background", "#1a1a2e")
        frame_rate = params.get("frame_rate")  # optional; None = leave Krita's default
        if width < 1 or width > 10000:
            return {"error_type": "INVALID_DIMENSIONS", "message": f"Invalid width: {width}", "recoverable": True, "request_id": request_id}
        if height < 1 or height > 10000:
            return {"error_type": "INVALID_DIMENSIONS", "message": f"Invalid height: {height}", "recoverable": True, "request_id": request_id}
        app = Krita.instance()
        try:
            doc = app.createDocument(width, height, name, "RGBA", "U8", "", 120.0)
        except Exception as e:
            return {"error_type": "DOCUMENT_CREATION_FAILED", "message": f"Failed to create document: {e}", "recoverable": False, "request_id": request_id}
        success, error = verifier.verify_document(doc, "new_canvas")
        if not success:
            return error
        window = app.activeWindow()
        if window:
            try:
                window.addView(doc)
            except Exception as e:
                return {"error_type": "VIEW_CREATION_FAILED", "message": f"Failed to add view: {e}", "recoverable": False, "request_id": request_id}
        success, error = verifier.verify_document_in_view(app, doc, "new_canvas")
        if not success:
            return error
        root = doc.rootNode()
        layer = doc.createNode("paint", "paintlayer")
        root.addChildNode(layer, None)
        doc.setActiveNode(layer)
        success, actual_layer, error = verifier.verify_layer_selected(doc, layer, "new_canvas")
        if not success:
            return error
        color = QColor(bg_color)
        r, g, b = color.red(), color.green(), color.blue()
        pixel_data = bytes([b, g, r, 255] * (width * height))
        layer.setPixelData(pixel_data, 0, 0, width, height)
        doc.refreshProjection()
        actual_width = doc.width()
        actual_height = doc.height()
        if actual_width != width or actual_height != height:
            return {"error_type": "DIMENSION_MISMATCH", "message": "Dimension mismatch", "requested_width": width, "requested_height": height, "actual_width": actual_width, "actual_height": actual_height, "recoverable": False, "request_id": request_id}
        actual_frame_rate = None
        if frame_rate:
            try:
                doc.setFramesPerSecond(int(frame_rate))
            except Exception as e:
                return {"error_type": "FRAME_RATE_SET_FAILED", "message": f"Failed to set frame rate: {e}", "recoverable": True, "request_id": request_id}
            actual_frame_rate = int(doc.framesPerSecond())
            if actual_frame_rate != int(frame_rate):
                return {"error_type": "FRAME_RATE_MISMATCH", "message": "Frame rate mismatch", "requested_frame_rate": frame_rate, "actual_frame_rate": actual_frame_rate, "recoverable": False, "request_id": request_id}
        return {"status": "ok", "width": actual_width, "height": actual_height, "name": name, "layer_name": actual_layer.name(), "frame_rate": actual_frame_rate, "verified": True, "request_id": request_id}

    def cmd_select_paint_layer(self, params, request_id=None):
        """P0.2: Select active paint layer WITH VERIFICATION."""
        verifier = StateVerifier(request_id)
        doc = self.get_active_document()
        success, error = verifier.verify_document(doc, "select_paint_layer")
        if not success:
            return error
        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error_type": "LAYER_NOT_FOUND", "message": "No paint layer found", "recoverable": False, "request_id": request_id}
        doc.setActiveNode(layer)
        success, actual_layer, error = verifier.verify_layer_selected(doc, layer, "select_paint_layer")
        if not success:
            return error
        return {"status": "ok", "layer_name": actual_layer.name(), "layer_type": actual_layer.type(), "verified": True, "request_id": request_id}

    def cmd_set_color(self, params):
        """Set foreground color."""
        color_hex = params.get("color", "#ffffff")

        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}

        color = QColor(color_hex)
        mc = ManagedColor.fromQColor(color, view.canvas())
        view.setForeGroundColor(mc)

        return {"status": "ok", "color": color_hex}

    def cmd_set_brush(self, params):
        """Set brush preset and size."""
        preset_name = params.get("preset", None)
        size = params.get("size", None)
        opacity = params.get("opacity", None)

        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}

        if preset_name:
            # Find brush preset
            presets = Krita.instance().resources("preset")
            found = None
            for name, preset in presets.items():
                if preset_name.lower() in name.lower():
                    found = preset
                    break
            if found:
                view.setCurrentBrushPreset(found)
            else:
                return {"error": f"Brush preset not found: {preset_name}"}

        if size is not None:
            self.current_brush_size = size
            view.setBrushSize(size)

        if opacity is not None:
            self.current_opacity = opacity
            # Opacity is set per-stroke, store for later

        return {"status": "ok", "preset": preset_name, "size": size, "opacity": opacity}

    def cmd_stroke(self, params):
        """Paint a stroke along points using pixel-level drawing with soft edges."""
        points = params.get("points", [])
        brush_size = params.get("size", self.current_brush_size)
        hardness = params.get("hardness", 0.5)  # 0.0 = very soft, 1.0 = hard edge
        opacity = params.get("opacity", 1.0)

        if len(points) < 2:
            return {"error": "Need at least 2 points for a stroke"}

        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active layer"}

        doc = self.get_active_document()
        view = self.get_active_view()

        if not view:
            return {"error": "No active view"}

        result = self._draw_stroke_pixels(layer, doc, view, points, brush_size, hardness, opacity)
        if "error" in result:
            return result

        doc.refreshProjection()
        return {"status": "ok", "points_count": len(points), "hardness": hardness}
    def cmd_fill(self, params):
        """Fill a circular area with current color."""
        x = params.get("x", 0)
        y = params.get("y", 0)
        radius = params.get("radius", 50)

        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active layer"}

        doc = self.get_active_document()
        view = self.get_active_view()

        if not view:
            return {"error": "No active view"}

        # Get current foreground color
        fg = view.foregroundColor()
        qcolor = fg.colorForCanvas(view.canvas())
        r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()

        # Paint a filled circle using pixel data
        # Create a bounding box
        x1 = max(0, x - radius)
        y1 = max(0, y - radius)
        x2 = min(doc.width(), x + radius)
        y2 = min(doc.height(), y + radius)
        w = x2 - x1
        h = y2 - y1

        if w <= 0 or h <= 0:
            return {"error": "Fill area out of bounds"}

        # Get existing pixel data
        existing = layer.pixelData(x1, y1, w, h)
        pixels = bytearray(existing)

        # Draw circle
        for py in range(h):
            for px in range(w):
                # Check if point is in circle
                dx = (x1 + px) - x
                dy = (y1 + py) - y
                if dx*dx + dy*dy <= radius*radius:
                    idx = (py * w + px) * 4
                    pixels[idx] = b      # B
                    pixels[idx+1] = g    # G
                    pixels[idx+2] = r    # R
                    pixels[idx+3] = 255  # A

        layer.setPixelData(bytes(pixels), x1, y1, w, h)
        doc.refreshProjection()

        return {"status": "ok", "x": x, "y": y, "radius": radius}

    def cmd_draw_shape(self, params):
        """Draw a shape (rectangle, ellipse, line)."""
        shape = params.get("shape", "rectangle")
        x = params.get("x", 0)
        y = params.get("y", 0)
        width = params.get("width", 100)
        height = params.get("height", 100)
        fill = params.get("fill", True)
        stroke = params.get("stroke", False)
        x2 = params.get("x2")
        y2 = params.get("y2")
        line_width = params.get("line_width", 2)

        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active layer"}

        doc = self.get_active_document()
        view = self.get_active_view()

        if not view:
            return {"error": "No active view"}

        # Get current foreground color
        fg = view.foregroundColor()
        qcolor = fg.colorForCanvas(view.canvas())
        r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()

        result = self._draw_shape_pixels(
            layer, doc, r, g, b, shape, x, y, width, height, fill, stroke, x2, y2, line_width
        )
        if "error" in result:
            return result

        doc.refreshProjection()
        return result

    def _draw_shape_pixels(self, layer, doc, r, g, b, shape, x, y, width, height,
                            fill, stroke, x2=None, y2=None, line_width=2):
        """Rasterize one shape onto layer's pixel data. Caller handles refreshProjection."""
        if shape == "line":
            x2 = x2 if x2 is not None else x + width
            y2 = y2 if y2 is not None else y + height

            # Calculate bounding box
            x1_bound = max(0, int(min(x, x2)) - line_width)
            y1_bound = max(0, int(min(y, y2)) - line_width)
            x2_bound = min(doc.width(), int(max(x, x2)) + line_width)
            y2_bound = min(doc.height(), int(max(y, y2)) + line_width)
            w = x2_bound - x1_bound
            h = y2_bound - y1_bound

            if w > 0 and h > 0:
                existing = layer.pixelData(x1_bound, y1_bound, w, h)
                pixels = bytearray(existing)

                # Draw line with thickness
                dist = max(abs(x2 - x), abs(y2 - y))
                steps = max(1, int(dist))
                radius = max(1, line_width // 2)

                for i in range(steps + 1):
                    t = i / steps if steps > 0 else 0
                    cx = x + t * (x2 - x)
                    cy = y + t * (y2 - y)
                    for dy in range(-radius, radius + 1):
                        for dx in range(-radius, radius + 1):
                            if dx*dx + dy*dy <= radius*radius:
                                px = int(cx) + dx - x1_bound
                                py = int(cy) + dy - y1_bound
                                if 0 <= px < w and 0 <= py < h:
                                    idx = (py * w + px) * 4
                                    pixels[idx] = b
                                    pixels[idx+1] = g
                                    pixels[idx+2] = r
                                    pixels[idx+3] = 255

                layer.setPixelData(bytes(pixels), x1_bound, y1_bound, w, h)
        elif shape == "rectangle" and fill:
            # Draw filled rectangle using pixel data
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2b = min(doc.width(), int(x + width))
            y2b = min(doc.height(), int(y + height))
            w = x2b - x1
            h = y2b - y1

            if w > 0 and h > 0:
                pixel_data = bytes([b, g, r, 255] * (w * h))
                layer.setPixelData(pixel_data, x1, y1, w, h)
        elif shape == "ellipse" and fill:
            # Draw filled ellipse using pixel data
            cx = x + width / 2
            cy = y + height / 2
            rx = width / 2
            ry = height / 2

            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2b = min(doc.width(), int(x + width))
            y2b = min(doc.height(), int(y + height))
            w = x2b - x1
            h = y2b - y1

            if w > 0 and h > 0:
                existing = layer.pixelData(x1, y1, w, h)
                pixels = bytearray(existing)

                for py in range(h):
                    for px in range(w):
                        # Check if point is in ellipse
                        dx = (x1 + px - cx) / rx if rx > 0 else 0
                        dy = (y1 + py - cy) / ry if ry > 0 else 0
                        if dx*dx + dy*dy <= 1:
                            idx = (py * w + px) * 4
                            pixels[idx] = b
                            pixels[idx+1] = g
                            pixels[idx+2] = r
                            pixels[idx+3] = 255

                layer.setPixelData(bytes(pixels), x1, y1, w, h)
        else:
            return {"error": f"Shape '{shape}' with current options not supported"}

        return {"status": "ok", "shape": shape}

    def cmd_get_canvas(self, params, request_id=None):
        """P0.6: Export canvas WITH VERIFICATION."""
        verifier = StateVerifier(request_id)
        filename = params.get("filename", "canvas.png")
        doc = self.get_active_document()
        success, error = verifier.verify_document(doc, "get_canvas")
        if not success:
            return error
        if not filename.endswith('.png'):
            filename += '.png'
        filepath = os.path.join(CANVAS_OUTPUT_DIR, filename)
        os.makedirs(CANVAS_OUTPUT_DIR, exist_ok=True)
        try:
            doc.setBatchmode(True)
            doc.exportImage(filepath, InfoObject())
            doc.setBatchmode(False)
        except Exception as e:
            return {"error_type": "EXPORT_FAILED", "message": f"Failed to export: {e}", "filepath": filepath, "recoverable": False, "request_id": request_id}
        success, file_stats, error = verifier.verify_file_created(filepath, min_size=100, operation="get_canvas")
        if not success:
            return error
        return {"status": "ok", "path": filepath, "filename": filename, "file_size": file_stats["file_size"], "verified": True, "request_id": request_id}

    def cmd_undo(self, params):
        """Undo last action."""
        app = Krita.instance()
        action = app.action('edit_undo')
        if action:
            action.trigger()
            return {"status": "ok"}
        return {"error": "Could not trigger undo"}

    def cmd_redo(self, params):
        """Redo last undone action."""
        app = Krita.instance()
        action = app.action('edit_redo')
        if action:
            action.trigger()
            return {"status": "ok"}
        return {"error": "Could not trigger redo"}

    def cmd_clear(self, params):
        """Clear the canvas."""
        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active layer"}

        doc = self.get_active_document()

        # Get canvas dimensions
        width = doc.width()
        height = doc.height()

        # Clear by filling with background color
        bg_color = params.get("color", "#1a1a2e")
        color = QColor(bg_color)
        r, g, b = color.red(), color.green(), color.blue()

        # Fill entire layer with color
        pixel_data = bytes([b, g, r, 255] * (width * height))
        layer.setPixelData(pixel_data, 0, 0, width, height)

        doc.refreshProjection()

        return {"status": "ok", "color": bg_color}

    def cmd_save(self, params, request_id=None):
        """P0.6: Save file WITH VERIFICATION."""
        verifier = StateVerifier(request_id)
        filepath = params.get("path")
        if not filepath:
            return {"error_type": "INVALID_PARAMETER", "message": "No path specified", "recoverable": True, "request_id": request_id}
        doc = self.get_active_document()
        success, error = verifier.verify_document(doc, "save")
        if not success:
            return error
        import os
        parent_dir = os.path.dirname(filepath)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                return {"error_type": "DIRECTORY_CREATION_FAILED", "message": f"Failed to create directory: {e}", "filepath": filepath, "recoverable": False, "request_id": request_id}
        try:
            doc.setBatchmode(True)
            doc.exportImage(filepath, InfoObject())
            doc.setBatchmode(False)
        except Exception as e:
            return {"error_type": "SAVE_FAILED", "message": f"Failed to save: {e}", "filepath": filepath, "recoverable": False, "request_id": request_id}
        success, file_stats, error = verifier.verify_file_created(filepath, min_size=100, operation="save")
        if not success:
            return error
        return {"status": "ok", "path": filepath, "file_size": file_stats["file_size"], "verified": True, "request_id": request_id}

    def cmd_get_color_at(self, params):
        """Get color at specific pixel (eyedropper)."""
        x = params.get("x", 0)
        y = params.get("y", 0)

        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        # Get projection pixel data at point
        layer = doc.rootNode()
        pixel_data = layer.projectionPixelData(x, y, 1, 1)

        if len(pixel_data) >= 4:
            # RGBA (BGRA byte order). QByteArray indexing returns length-1
            # byte chunks, plain bytes indexing returns ints — normalize both.
            def ch(i):
                v = pixel_data[i]
                if isinstance(v, int):
                    return v
                return int(bytes(v)[0])

            b, g, r, a = ch(0), ch(1), ch(2), ch(3)
            hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b)
            return {"status": "ok", "color": hex_color, "r": r, "g": g, "b": b, "a": a}

        return {"error": "Could not read pixel"}

    def cmd_list_brushes(self, params):
        """List available brush presets."""
        filter_str = params.get("filter", "")
        limit = params.get("limit", 50)

        presets = Krita.instance().resources("preset")
        brush_list = []

        for name, preset in presets.items():
            if filter_str.lower() in name.lower():
                brush_list.append(name)
                if len(brush_list) >= limit:
                    break

        return {"status": "ok", "brushes": brush_list, "count": len(brush_list)}

    def cmd_open_file(self, params):
        """Open an existing file in Krita."""
        filepath = params.get("path")
        if not filepath:
            return {"error": "No path specified"}

        if not os.path.exists(filepath):
            return {"error": f"File not found: {filepath}"}

        app = Krita.instance()

        # Open the document
        doc = app.openDocument(filepath)
        if not doc:
            return {"error": f"Failed to open: {filepath}"}

        # Add view to active window
        window = app.activeWindow()
        if window:
            window.addView(doc)

        return {"status": "ok", "path": filepath, "name": doc.name(), "width": doc.width(), "height": doc.height()}

    # --- Animation frame/keyframe helpers ---
    def cmd_create_keyframe(self, params, request_id=None):
        """P0.4: Create keyframe WITH RETRY AND VERIFICATION."""
        verifier = StateVerifier(request_id)
        doc = self.get_active_document()
        success, error = verifier.verify_document(doc, "create_keyframe")
        if not success:
            return error
        node = self._ensure_active_paint_layer()
        if not node:
            return {"error_type": "LAYER_NOT_FOUND", "message": "No active paint layer", "recoverable": False, "request_id": request_id}
        frame = int(params.get("frame", self._get_current_time(doc)))
        success, exists, _ = verifier.verify_keyframe_exists(node, doc, frame, "create_keyframe_precheck")
        if success and exists:
            return {"status": "ok", "created_frame": frame, "current_frame": self._get_current_time(doc), "keyframes": self._list_keyframes(node, doc), "already_existed": True, "verified": True, "request_id": request_id}
        max_attempts = 2
        for attempt in range(max_attempts):
            verifier.log(f"Keyframe creation attempt {attempt + 1}/{max_attempts}")
            self._create_keyframe(node, doc, frame)
            success, exists, _ = verifier.verify_keyframe_exists(node, doc, frame, "create_keyframe_verify")
            if success and exists:
                verifier.log(f"Keyframe verified on attempt {attempt + 1}")
                return {"status": "ok", "created_frame": frame, "current_frame": self._get_current_time(doc), "keyframes": self._list_keyframes(node, doc), "attempts": attempt + 1, "verified": True, "request_id": request_id}
            if attempt < max_attempts - 1:
                QApplication.processEvents()
        verifier.log(f"Keyframe creation failed after {max_attempts} attempts")
        return {"error_type": "KEYFRAME_CREATION_FAILED", "message": f"Failed to create keyframe after {max_attempts} attempts", "requested_frame": frame, "current_frame": self._get_current_time(doc), "keyframes": self._list_keyframes(node, doc), "attempts": max_attempts, "recoverable": True, "debug": self._diagnose_timeline(doc), "request_id": request_id, "known_limitation": "Krita keyframe API has known reliability issues"}

    def _diagnose_timeline(self, doc):
        """Collect diagnostics about the animation/timeline state (for debugging)."""
        out = {}
        node = self._get_active_paint_layer()
        out["active_layer"] = node.name() if node else None
        out["animated"] = bool(node.animated()) if node else None
        out["has_keyframe_at_time_api"] = callable(getattr(node, "hasKeyframeAtTime", None)) if node else None
        try:
            out["animation_length"] = int(doc.animationLength())
        except Exception as e:
            out["animation_length"] = f"err:{e}"
        try:
            out["current_time"] = int(doc.currentTime())
        except Exception as e:
            out["current_time"] = f"err:{e}"
        out["timeline_view"] = None
        view = self._timeline_view()
        if view is not None:
            model = view.model()
            row_names = []
            if model is not None:
                for r in range(model.rowCount()):
                    try:
                        row_names.append(str(model.data(model.index(r, 0))))
                    except Exception as e:
                        row_names.append(f"err:{e}")
            out["timeline_view"] = {
                "rows": model.rowCount() if model else None,
                "cols": model.columnCount() if model else None,
                "row_names": row_names,
                "row_count": view.selectionModel().selectedRows().__len__() if view.selectionModel() else None,
            }
            out["active_layer_row"] = self._active_layer_row(view)
        for name in ("add_blank_frame", "add_duplicate_frame", "remove_frames"):
            action = Krita.instance().action(name)
            out[f"action_{name}"] = (action is not None, action.isEnabled() if action else None)
        return out

    def cmd_set_current_frame(self, params, request_id=None):
        """P0.3: Set timeline current frame WITH VERIFICATION."""
        verifier = StateVerifier(request_id)
        doc = self.get_active_document()
        success, error = verifier.verify_document(doc, "set_current_frame")
        if not success:
            return error
        frame = int(params.get("frame", 0))
        try:
            doc.setCurrentTime(frame)
        except Exception as e:
            return {"error_type": "FRAME_SELECTION_FAILED", "message": f"Failed to set frame: {e}", "requested_frame": frame, "recoverable": True, "request_id": request_id}
        success, actual_frame, error = verifier.verify_frame_selected(doc, frame, "set_current_frame")
        if not success:
            return error
        node = self._get_active_paint_layer()
        keyframes = self._list_keyframes(node, doc) if node else []
        return {"status": "ok", "current_frame": actual_frame, "verified": True, "keyframes": keyframes, "request_id": request_id}

    def cmd_get_current_frame(self, params):
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}
        try:
            current = self._get_current_time(doc)
            node = self._get_active_paint_layer()
            keyframes = self._list_keyframes(node, doc) if node else []
            return {"status": "ok", "current_frame": current, "keyframes": keyframes}
        except Exception as e:
            return {"error": str(e)}

    def cmd_configure_animation(self, params, request_id=None):
        """Set frame rate and/or playback range on the CURRENT active
        document (does not create or resize any canvas). Both params are
        optional; omit either to leave it unchanged."""
        doc = self.get_active_document()
        if not doc:
            return {"error_type": "DOCUMENT_NOT_FOUND", "message": "No active document", "recoverable": False, "request_id": request_id}

        frame_rate = params.get("frame_rate")
        playback_end = params.get("playback_end")
        playback_start = params.get("playback_start", 0)

        if frame_rate is not None:
            try:
                doc.setFramesPerSecond(int(frame_rate))
            except Exception as e:
                return {"error_type": "FRAME_RATE_SET_FAILED", "message": f"Failed to set frame rate: {e}", "recoverable": True, "request_id": request_id}

        if playback_end is not None:
            try:
                doc.setPlayBackRange(int(playback_start), int(playback_end))
            except Exception as e:
                return {"error_type": "PLAYBACK_RANGE_SET_FAILED", "message": f"Failed to set playback range: {e}", "recoverable": True, "request_id": request_id}

        return {
            "status": "ok",
            "frame_rate": int(doc.framesPerSecond()),
            "playback_start": int(doc.playBackStartTime()),
            "playback_end": int(doc.playBackEndTime()),
            "animation_length": int(doc.animationLength()),
            "request_id": request_id,
        }

    def cmd_list_keyframes(self, params):
        """List keyframes on the active paint layer."""
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        node = self._get_active_paint_layer()
        if not node:
            return {"error": "No active paint layer"}

        try:
            return {
                "status": "ok",
                "current_frame": self._get_current_time(doc),
                "keyframes": self._list_keyframes(node, doc),
            }
        except Exception as e:
            return {"error": str(e)}

    def cmd_delete_keyframe(self, params):
        """Delete keyframe on the active paint layer."""
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        node = self._get_active_paint_layer()
        if not node:
            return {"error": "No active paint layer"}

        frame = int(params.get("frame", self._get_current_time(doc)))
        try:
            deleted = self._delete_keyframe(node, doc, frame)
            keyframes = self._list_keyframes(node, doc)
            if not deleted:
                return {
                    "error": "Failed to delete keyframe",
                    "requested_frame": frame,
                    "current_frame": self._get_current_time(doc),
                    "keyframes": keyframes,
                }
            return {
                "status": "ok",
                "deleted_frame": frame,
                "current_frame": self._get_current_time(doc),
                "keyframes": keyframes,
            }
        except Exception as e:
            return {"error": str(e)}

    def cmd_has_keyframe(self, params):
        """Check whether a keyframe exists at frame on active paint layer."""
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        node = self._get_active_paint_layer()
        if not node:
            return {"error": "No active paint layer"}

        frame = int(params.get("frame", self._get_current_time(doc)))
        try:
            return {
                "status": "ok",
                "frame": frame,
                "exists": self._has_keyframe(node, doc, frame),
                "keyframes": self._list_keyframes(node, doc),
            }
        except Exception as e:
            return {"error": str(e)}

    # Backward-compatible wrappers
    def cmd_create_frame(self, params):
        frame = params.get("frame", None)
        if frame is None:
            doc = self.get_active_document()
            if not doc:
                return {"error": "No active document"}
            frame = self._get_current_time(doc)
        return self.cmd_create_keyframe({"frame": int(frame)})

    def cmd_select_frame(self, params):
        frame = params.get("frame", params.get("index", 0))
        return self.cmd_set_current_frame({"frame": int(frame)})

    def cmd_enable_onion(self, params):
        enabled = params.get("enabled", True)
        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}
        try:
            view.setOnionSkinEnabled(enabled)
            return {"status": "ok", "onion": enabled}
        except Exception as e:
            return {"error": str(e)}

    def cmd_inspect_previous_frame(self, params):
        """Return a small downsampled color grid representing the previous frame for reference."""
        downscale = params.get("downscale", 32)
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}

        try:
            current = int(doc.currentTime())
            prev = max(0, current - 1)

            # Temporarily sample the previous frame's projection pixels
            root = doc.rootNode()
            width = doc.width()
            height = doc.height()

            # Compute sampling grid
            grid_w = downscale
            grid_h = max(1, int(downscale * height / max(1, width)))
            step_x = max(1, width // grid_w)
            step_y = max(1, height // grid_h)

            # Switch to previous frame temporarily
            doc.setCurrentTime(prev)
            # Read projection pixel data for sampled points
            samples = []
            layer = root
            for gy in range(0, height, step_y):
                row = []
                for gx in range(0, width, step_x):
                    pdata = layer.projectionPixelData(gx, gy, 1, 1)
                    if len(pdata) >= 3:
                        b, g, r = pdata[0], pdata[1], pdata[2]
                        row.append('#{:02x}{:02x}{:02x}'.format(r, g, b))
                    else:
                        row.append('#000000')
                samples.append(row)

            # Restore current frame
            doc.setCurrentTime(current)

            return {"status": "ok", "grid": samples}
        except Exception as e:
            return {"error": str(e)}




    def cmd_list_layers(self, params):
        """
        List all layers in the current document (READ-ONLY).
        
        Returns structured information about all layers including:
        - name, type, visibility, opacity
        - hierarchy (parent/child relationships)
        - whether each layer is the active layer
        - layer identifiers/indices
        
        This operation is strictly read-only and does not modify any state.
        """
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}
        
        try:
            active_node = doc.activeNode()
            active_uuid = str(active_node.uniqueId()) if active_node else None
            
            def serialize_node(node, parent_name=None, depth=0):
                """Recursively serialize a node and its children."""
                try:
                    # Get basic properties
                    node_data = {
                        "name": node.name(),
                        "type": node.type(),
                        "visible": node.visible(),
                        "opacity": int(node.opacity()),  # 0-255
                        "locked": node.locked() if hasattr(node, "locked") else False,
                        "uuid": str(node.uniqueId()),
                        "is_active": str(node.uniqueId()) == active_uuid,
                        "depth": depth,
                        "parent": parent_name
                    }
                    
                    # Add animation info if available
                    if hasattr(node, "animated"):
                        try:
                            node_data["animated"] = bool(node.animated())
                        except:
                            node_data["animated"] = False
                    
                    # Recursively process children for group layers
                    children = node.childNodes() if hasattr(node, "childNodes") else []
                    if children:
                        node_data["children"] = [
                            serialize_node(child, node.name(), depth + 1)
                            for child in children
                        ]
                    
                    return node_data
                except Exception as e:
                    return {
                        "name": str(node),
                        "type": "unknown",
                        "error": str(e),
                        "depth": depth
                    }
            
            # Start from root and serialize all layers
            root = doc.rootNode()
            layers = []
            
            # Process all child nodes of root
            for child in root.childNodes():
                layers.append(serialize_node(child, None, 0))
            
            return {
                "status": "ok",
                "layers": layers,
                "layer_count": len(layers),
                "active_layer_uuid": active_uuid
            }
            
        except Exception as e:
            return {"error": f"Failed to list layers: {str(e)}"}

    def cmd_get_canvas_info(self, params):
        """
        Get canvas/document metadata (READ-ONLY).
        
        Returns:
        - Canvas dimensions (width, height in pixels)
        - Color model and bit depth
        - Document name
        - Current frame/time (for animations)
        - Animation metadata if available
        
        This operation is strictly read-only and does not modify any state.
        """
        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}
        
        try:
            info = {
                "status": "ok",
                "width": doc.width(),
                "height": doc.height(),
                "name": doc.name(),
                "filename": doc.fileName() if doc.fileName() else None,
                "resolution": doc.resolution(),
                "color_model": doc.colorModel(),
                "color_depth": doc.colorDepth(),
                "color_profile": doc.colorProfile()
            }
            
            # Add animation information
            try:
                info["current_frame"] = int(doc.currentTime())
                info["animation_length"] = int(doc.animationLength())
                info["playback_start"] = int(doc.playBackStartTime())
                info["playback_end"] = int(doc.playBackEndTime())
                info["frame_rate"] = int(doc.framesPerSecond())
            except Exception as e:
                info["animation_error"] = str(e)
            
            # Add active layer info
            active_node = doc.activeNode()
            if active_node:
                info["active_layer"] = {
                    "name": active_node.name(),
                    "type": active_node.type(),
                    "uuid": active_node.uniqueId()
                }
            
            # Add document modification state
            try:
                info["modified"] = doc.modified()
            except:
                pass
            
            return info
            
        except Exception as e:
            return {"error": f"Failed to get canvas info: {str(e)}"}

    def cmd_draw_path(self, params):
        """Render connected cubic Bezier segments as one raster stroke."""
        segments = params.get("segments", [])
        if not segments:
            return {"error": "No path segments provided"}

        layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active paint layer"}

        doc = self.get_active_document()
        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}

        samples = max(4, min(128, int(params.get("samples_per_segment", 24))))
        brush_size = params.get("brush_size", self.current_brush_size)
        opacity = float(params.get("opacity", 1.0))
        hardness = float(params.get("hardness", 0.5))

        color_hex = params.get("color")
        if color_hex:
            try:
                color = QColor(color_hex)
                view.setForeGroundColor(ManagedColor.fromQColor(color, view.canvas()))
            except Exception as e:
                return {"error": f"Invalid color {color_hex}: {e}"}

        points, error = self._sample_bezier_segments(segments, samples)
        if error:
            return {"error": error}

        result = self._draw_stroke_pixels(
            layer, doc, view, points, brush_size, hardness, opacity
        )
        if "error" in result:
            return result

        doc.refreshProjection()
        return {
            "status": "ok",
            "segments_drawn": len(segments),
            "points_sampled": len(points),
            "errors": None
        }

    def _sample_bezier_segments(self, segments, samples):
        """Sample connected cubic Bezier segments into a flat polyline.

        Returns (points, None) on success or (None, error_message) on failure.
        """
        points = []
        try:
            for index, segment in enumerate(segments):
                start = segment["start"]
                control1 = segment["control1"]
                control2 = segment["control2"]
                end = segment["end"]

                if index and points:
                    previous = points[-1]
                    if abs(previous[0] - start[0]) > 1e-6 or abs(previous[1] - start[1]) > 1e-6:
                        return None, f"Segment {index} is not connected to the previous segment"

                for step in range(samples + 1):
                    if index and step == 0:
                        continue
                    t = step / samples
                    inverse = 1.0 - t
                    points.append([
                        inverse ** 3 * start[0]
                        + 3 * inverse ** 2 * t * control1[0]
                        + 3 * inverse * t ** 2 * control2[0]
                        + t ** 3 * end[0],
                        inverse ** 3 * start[1]
                        + 3 * inverse ** 2 * t * control1[1]
                        + 3 * inverse * t ** 2 * control2[1]
                        + t ** 3 * end[1]
                    ])
        except (KeyError, TypeError, ValueError, IndexError) as e:
            return None, f"Invalid path segment: {e}"

        return points, None

    def cmd_bulk_strokes(self, params):
        """
        Execute multiple strokes in one operation.
        
        This significantly reduces communication overhead by processing
        multiple strokes locally within Krita without round-trips for each stroke.
        
        Each stroke can specify its own color, brush size, and other properties.
        """
        strokes = params.get("strokes", [])
        
        if not strokes:
            log("bulk_strokes: No strokes provided")
            return {"error": "No strokes provided"}
        
        layer = self._ensure_active_paint_layer()
        if not layer:
            log("bulk_strokes: No active paint layer")
            return {"error": "No active paint layer"}
        
        doc = self.get_active_document()
        view = self.get_active_view()
        
        if not view:
            log("bulk_strokes: No active view")
            return {"error": "No active view"}
        
        strokes_drawn = 0
        strokes_failed = 0
        errors = []
        
        # Process each stroke
        for stroke_idx, stroke_data in enumerate(strokes):
            try:
                points = stroke_data.get("points", [])
                if len(points) < 2:
                    strokes_failed += 1
                    errors.append(f"Stroke {stroke_idx}: Need at least 2 points")
                    continue
                
                # Set color if provided
                color_hex = stroke_data.get("color")
                if color_hex:
                    try:
                        color = QColor(color_hex)
                        mc = ManagedColor.fromQColor(color, view.canvas())
                        view.setForeGroundColor(mc)
                    except Exception as e:
                        strokes_failed += 1
                        errors.append(f"Stroke {stroke_idx}: Invalid color {color_hex}: {e}")
                        continue
                
                # Set brush size if provided
                brush_size = stroke_data.get("brush_size", self.current_brush_size)
                if brush_size:
                    self.current_brush_size = brush_size
                
                # Get stroke parameters
                pressure = stroke_data.get("pressure", 1.0)
                hardness = stroke_data.get("hardness", 0.5)
                opacity = stroke_data.get("opacity", 1.0)
                
                # Draw the stroke using existing pixel-level logic
                result = self._draw_stroke_pixels(
                    layer, doc, view, points, brush_size, hardness, opacity
                )
                
                if "error" in result:
                    strokes_failed += 1
                    errors.append(f"Stroke {stroke_idx}: {result['error']}")
                else:
                    strokes_drawn += 1
                    
            except Exception as e:
                strokes_failed += 1
                errors.append(f"Stroke {stroke_idx}: {str(e)}")
        
        # Single projection refresh for all strokes
        doc.refreshProjection()
        
        result = {
            "status": "ok" if strokes_failed == 0 else "partial",
            "strokes_drawn": strokes_drawn,
            "strokes_failed": strokes_failed,
            "total_strokes": len(strokes),
            "errors": errors if errors else None
        }
        
        return result

    def cmd_draw_scene(self, params, request_id=None):
        """
        Execute a batch of heterogeneous geometry elements (paths, strokes, shapes)
        as one document-level operation with a single projection refresh.

        This is a deterministic executor only: Claude supplies fully explicit
        geometry (points, control points, color, width, opacity, hardness) per
        element, in the order it should be drawn. The MCP does not interpret,
        plan, or decide any of that content - it just draws exactly what it is
        given, in one round trip instead of one call per element.

        elements: list of dicts, each with a "type":
          - "path":   {segments: [...bezier segments like draw_path...], color,
                       brush_size, opacity, hardness, samples_per_segment}
          - "stroke": {points: [[x,y], ...], color, brush_size, opacity, hardness}
          - "shape":  {shape: rectangle|ellipse|line, x, y, width, height, fill,
                       stroke, x2, y2, line_width, color}
        layer (optional): paint layer name to draw all elements onto; created if
          it doesn't exist yet. Omit to use the currently active paint layer.
        """
        elements = params.get("elements", [])
        if not elements:
            return {"error": "No elements provided"}

        doc = self.get_active_document()
        if not doc:
            return {"error": "No active document"}

        layer_name = params.get("layer")
        if layer_name:
            layer = self._ensure_named_paint_layer(doc, layer_name)
        else:
            layer = self._ensure_active_paint_layer()
        if not layer:
            return {"error": "No active paint layer"}

        view = self.get_active_view()
        if not view:
            return {"error": "No active view"}

        results = []
        drawn = 0
        failed = 0

        for index, element in enumerate(elements):
            elem_type = element.get("type", "stroke")
            try:
                color_hex = element.get("color")
                if color_hex:
                    color = QColor(color_hex)
                    if not color.isValid():
                        raise ValueError(f"Invalid color {color_hex}")
                    view.setForeGroundColor(ManagedColor.fromQColor(color, view.canvas()))

                if elem_type == "path":
                    samples = max(4, min(128, int(element.get("samples_per_segment", 24))))
                    path_points, error = self._sample_bezier_segments(element.get("segments", []), samples)
                    if error:
                        raise ValueError(error)
                    brush_size = element.get("brush_size", element.get("width", self.current_brush_size))
                    opacity = float(element.get("opacity", 1.0))
                    hardness = float(element.get("hardness", 0.5))
                    draw_result = self._draw_stroke_pixels(layer, doc, view, path_points, brush_size, hardness, opacity)
                    if "error" in draw_result:
                        raise ValueError(draw_result["error"])
                    results.append({"index": index, "type": "path", "status": "ok", "points_sampled": len(path_points)})

                elif elem_type == "stroke":
                    stroke_points = element.get("points", [])
                    if len(stroke_points) < 2:
                        raise ValueError("Need at least 2 points for a stroke")
                    brush_size = element.get("brush_size", element.get("width", self.current_brush_size))
                    opacity = float(element.get("opacity", 1.0))
                    hardness = float(element.get("hardness", 0.5))
                    draw_result = self._draw_stroke_pixels(layer, doc, view, stroke_points, brush_size, hardness, opacity)
                    if "error" in draw_result:
                        raise ValueError(draw_result["error"])
                    results.append({"index": index, "type": "stroke", "status": "ok", "points_count": len(stroke_points)})

                elif elem_type == "shape":
                    fg = view.foregroundColor()
                    qcolor = fg.colorForCanvas(view.canvas())
                    r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()
                    shape_result = self._draw_shape_pixels(
                        layer, doc, r, g, b,
                        element.get("shape", "rectangle"),
                        element.get("x", 0), element.get("y", 0),
                        element.get("width", 100), element.get("height", 100),
                        element.get("fill", True), element.get("stroke", False),
                        element.get("x2"), element.get("y2"),
                        element.get("line_width", 2)
                    )
                    if "error" in shape_result:
                        raise ValueError(shape_result["error"])
                    results.append({"index": index, "type": "shape", "status": "ok"})

                else:
                    raise ValueError(f"Unknown element type '{elem_type}'")

                drawn += 1
            except Exception as e:
                failed += 1
                results.append({"index": index, "type": elem_type, "status": "error", "error": str(e)})

        doc.refreshProjection()

        return {
            "status": "ok" if failed == 0 else "partial",
            "elements_drawn": drawn,
            "elements_failed": failed,
            "total_elements": len(elements),
            "layer_name": layer.name(),
            "results": results
        }

    def _ensure_named_paint_layer(self, doc, name):
        """Find a paint layer by name (creating it if needed) and activate it."""
        root = doc.rootNode()

        def find(node):
            for child in node.childNodes() or []:
                try:
                    if child.name() == name and child.type() == "paintlayer":
                        return child
                except Exception:
                    pass
                found = find(child)
                if found:
                    return found
            return None

        layer = find(root)
        if not layer:
            layer = doc.createNode(name, "paintlayer")
            root.addChildNode(layer, None)
        doc.setActiveNode(layer)
        return layer

    def _draw_stroke_pixels(self, layer, doc, view, points, brush_size, hardness, opacity):
        """
        Draw a stroke (already-flattened polyline) using pixel operations.

        Shared by cmd_stroke, cmd_bulk_strokes, cmd_draw_path, and cmd_draw_scene
        so every drawing tool renders through one code path. Prefers a vectorized
        numpy implementation (fast, anti-aliased edges); falls back to the
        original scalar per-pixel loop if numpy is unavailable or errors.
        """
        if _HAS_NUMPY:
            try:
                return self._draw_stroke_pixels_np(layer, doc, view, points, brush_size, hardness, opacity)
            except Exception as e:
                log(f"_draw_stroke_pixels: numpy path failed ({e}), falling back to scalar renderer")
        return self._draw_stroke_pixels_scalar(layer, doc, view, points, brush_size, hardness, opacity)

    def _draw_stroke_pixels_np(self, layer, doc, view, points, brush_size, hardness, opacity):
        """Vectorized stroke rasterizer: one cached anti-aliased mask, stamped via numpy slicing."""
        fg = view.foregroundColor()
        qcolor = fg.colorForCanvas(view.canvas())
        col_r, col_g, col_b = qcolor.red(), qcolor.green(), qcolor.blue()

        canvas_w = doc.width()
        canvas_h = doc.height()
        radius = max(1, brush_size // 2)

        min_x = max(0, int(min(p[0] for p in points)) - radius - 2)
        min_y = max(0, int(min(p[1] for p in points)) - radius - 2)
        max_x = min(canvas_w, int(max(p[0] for p in points)) + radius + 2)
        max_y = min(canvas_h, int(max(p[1] for p in points)) + radius + 2)

        w = max_x - min_x
        h = max_y - min_y
        if w <= 0 or h <= 0:
            return {"error": "Stroke out of bounds"}

        existing = layer.pixelData(min_x, min_y, w, h)
        pixels = np.frombuffer(existing, dtype=np.uint8).reshape(h, w, 4).copy()

        mask = _make_stamp_mask(radius, round(float(hardness), 3))
        mask_size = mask.shape[0]
        opacity = float(opacity)

        # Densify consecutive points so fast-moving segments don't leave gaps
        # between stamps (mirrors the previous draw_line interpolation).
        stamped = []
        step_limit = max(1, radius // 3)
        for i, p in enumerate(points):
            if i > 0:
                x1, y1 = points[i - 1]
                x2, y2 = p
                dist = math.hypot(x2 - x1, y2 - y1)
                steps = max(1, int(dist / step_limit))
                for s in range(1, steps + 1):
                    t = s / steps
                    stamped.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
            else:
                stamped.append((p[0], p[1]))

        color_bgr = np.array([col_b, col_g, col_r], dtype=np.float32)

        for cx, cy in stamped:
            cx = int(round(cx))
            cy = int(round(cy))

            tx0 = cx - radius - min_x
            ty0 = cy - radius - min_y

            src_x0 = max(0, -tx0)
            src_y0 = max(0, -ty0)
            dst_x0 = max(0, tx0)
            dst_y0 = max(0, ty0)
            dst_x1 = min(w, tx0 + mask_size)
            dst_y1 = min(h, ty0 + mask_size)

            if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
                continue

            src_x1 = src_x0 + (dst_x1 - dst_x0)
            src_y1 = src_y0 + (dst_y1 - dst_y0)

            alpha = mask[src_y0:src_y1, src_x0:src_x1] * opacity
            if alpha.size == 0:
                continue
            alpha3 = alpha[..., None]

            region = pixels[dst_y0:dst_y1, dst_x0:dst_x1]
            existing_bgr = region[..., :3].astype(np.float32)
            blended_bgr = existing_bgr * (1.0 - alpha3) + color_bgr * alpha3

            existing_a = region[..., 3].astype(np.float32)
            new_a = np.maximum(existing_a, alpha * 255.0)

            region[..., :3] = blended_bgr.astype(np.uint8)
            region[..., 3] = new_a.astype(np.uint8)

        layer.setPixelData(pixels.tobytes(), min_x, min_y, w, h)
        return {"status": "ok", "points_count": len(points)}

    def _draw_stroke_pixels_scalar(self, layer, doc, view, points, brush_size, hardness, opacity):
        """
        Original pure-Python per-pixel stroke rasterizer. Kept as a fallback for
        environments where numpy is unavailable in Krita's bundled Python.
        """
        # Get current foreground color
        fg = view.foregroundColor()
        qcolor = fg.colorForCanvas(view.canvas())
        r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()

        width = doc.width()
        height = doc.height()
        radius = max(1, brush_size // 2)

        # Calculate bounding box for all points plus brush radius
        min_x = max(0, int(min(p[0] for p in points)) - radius - 2)
        min_y = max(0, int(min(p[1] for p in points)) - radius - 2)
        max_x = min(width, int(max(p[0] for p in points)) + radius + 2)
        max_y = min(height, int(max(p[1] for p in points)) + radius + 2)

        w = max_x - min_x
        h = max_y - min_y

        if w <= 0 or h <= 0:
            return {"error": "Stroke out of bounds"}

        # Get existing pixel data for the affected region
        existing = layer.pixelData(min_x, min_y, w, h)
        pixels = bytearray(existing)

        def draw_soft_circle(cx, cy, point_opacity=1.0):
            """Draw a soft circle with falloff at canvas coordinates."""
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    dist_sq = dx*dx + dy*dy
                    if dist_sq <= radius*radius:
                        px = int(cx) + dx - min_x
                        py = int(cy) + dy - min_y
                        if 0 <= px < w and 0 <= py < h:
                            dist = math.sqrt(dist_sq) / radius if radius > 0 else 0
                            
                            if hardness >= 1.0:
                                alpha_factor = 1.0
                            else:
                                if dist < hardness:
                                    alpha_factor = 1.0
                                else:
                                    falloff = (dist - hardness) / (1.0 - hardness) if hardness < 1.0 else 0
                                    alpha_factor = 1.0 - falloff
                            
                            final_alpha = int(255 * alpha_factor * opacity * point_opacity)
                            
                            if final_alpha > 0:
                                idx = (py * w + px) * 4
                                existing_b = pixels[idx]
                                existing_g = pixels[idx+1]
                                existing_r = pixels[idx+2]
                                existing_a = pixels[idx+3]
                                
                                blend = final_alpha / 255.0
                                new_r = int(existing_r * (1 - blend) + r * blend)
                                new_g = int(existing_g * (1 - blend) + g * blend)
                                new_b = int(existing_b * (1 - blend) + b * blend)
                                new_a = max(existing_a, final_alpha)
                                
                                pixels[idx] = new_b
                                pixels[idx+1] = new_g
                                pixels[idx+2] = new_r
                                pixels[idx+3] = new_a
        
        def draw_line(x1, y1, x2, y2):
            """Draw a line using interpolation with soft brush circles."""
            dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            steps = max(1, int(dist / max(1, radius / 3)))
            
            for i in range(steps + 1):
                t = i / steps if steps > 0 else 0
                x = x1 + t * (x2 - x1)
                y = y1 + t * (y2 - y1)
                draw_soft_circle(x, y)
        
        # Draw soft circles at each point and lines between them
        for i in range(len(points)):
            draw_soft_circle(points[i][0], points[i][1])
            if i > 0:
                draw_line(points[i-1][0], points[i-1][1], points[i][0], points[i][1])
        
        # Write pixels back to layer (but don't refresh projection yet)
        layer.setPixelData(bytes(pixels), min_x, min_y, w, h)
        
        return {"status": "ok", "points_count": len(points)}


# Register the extension
Krita.instance().addExtension(KritaMCPExtension(Krita.instance()))
