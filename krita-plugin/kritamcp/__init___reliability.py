# RELIABILITY HARDENED VERSION - P0 Implementation
# This file contains the state verification framework and critical fixes
# To be integrated into __init__.py

import uuid

# =============================================================================
# STATE VERIFICATION FRAMEWORK (P0.1)
# =============================================================================

class StateVerifier:
    """
    Reusable state verification mechanism for Krita operations.
    
    Provides systematic verification of document, layer, and frame state
    after operations to prevent silent failures.
    """
    
    def __init__(self, request_id=None):
        self.request_id = request_id or str(uuid.uuid4())[:8]
    
    def log(self, message):
        """Log with request ID."""
        print(f"[StateVerifier:{self.request_id}] {message}", file=sys.stderr, flush=True)
    
    def verify_document(self, doc, operation="operation"):
        """
        Verify document exists and is valid.
        
        Returns: (success: bool, error_dict or None)
        """
        if doc is None:
            self.log(f"{operation}: Document is None")
            return False, {
                "error_type": "DOCUMENT_NOT_FOUND",
                "message": "No active document",
                "recoverable": False,
                "request_id": self.request_id
            }
        
        try:
            # Verify document is accessible
            _ = doc.width()
            _ = doc.height()
            return True, None
        except Exception as e:
            self.log(f"{operation}: Document invalid: {e}")
            return False, {
                "error_type": "DOCUMENT_INVALID",
                "message": f"Document not accessible: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_view(self, view, operation="operation"):
        """
        Verify view exists and is valid.
        
        Returns: (success: bool, error_dict or None)
        """
        if view is None:
            self.log(f"{operation}: View is None")
            return False, {
                "error_type": "VIEW_NOT_FOUND",
                "message": "No active view",
                "recoverable": False,
                "request_id": self.request_id
            }
        
        return True, None
    
    def verify_layer(self, layer, operation="operation"):
        """
        Verify layer exists and is valid.
        
        Returns: (success: bool, error_dict or None)
        """
        if layer is None:
            self.log(f"{operation}: Layer is None")
            return False, {
                "error_type": "LAYER_NOT_FOUND",
                "message": "No paint layer found",
                "recoverable": False,
                "request_id": self.request_id
            }
        
        try:
            # Verify layer is accessible
            _ = layer.name()
            _ = layer.type()
            return True, None
        except Exception as e:
            self.log(f"{operation}: Layer invalid: {e}")
            return False, {
                "error_type": "LAYER_INVALID",
                "message": f"Layer not accessible: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_layer_selected(self, doc, expected_layer, operation="select_layer"):
        """
        Verify that expected_layer is actually the active layer.
        
        Returns: (success: bool, actual_layer, error_dict or None)
        """
        try:
            actual_layer = doc.activeNode()
            
            if actual_layer is None:
                self.log(f"{operation}: Active layer is None after selection")
                return False, None, {
                    "error_type": "LAYER_SELECTION_FAILED",
                    "message": "Layer selection failed - no active layer",
                    "expected_layer": expected_layer.name() if expected_layer else None,
                    "actual_layer": None,
                    "recoverable": True,
                    "request_id": self.request_id
                }
            
            if actual_layer != expected_layer:
                self.log(f"{operation}: Layer mismatch - expected {expected_layer.name()}, got {actual_layer.name()}")
                return False, actual_layer, {
                    "error_type": "LAYER_SELECTION_MISMATCH",
                    "message": "Layer selection mismatch",
                    "expected_layer": expected_layer.name(),
                    "actual_layer": actual_layer.name(),
                    "recoverable": True,
                    "request_id": self.request_id
                }
            
            self.log(f"{operation}: Layer verified: {actual_layer.name()}")
            return True, actual_layer, None
            
        except Exception as e:
            self.log(f"{operation}: Layer verification failed: {e}")
            return False, None, {
                "error_type": "LAYER_VERIFICATION_ERROR",
                "message": f"Layer verification error: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_frame_selected(self, doc, expected_frame, operation="set_frame"):
        """
        Verify that expected_frame is actually the current frame.
        
        Returns: (success: bool, actual_frame, error_dict or None)
        """
        try:
            actual_frame = int(doc.currentTime())
            
            if actual_frame != expected_frame:
                self.log(f"{operation}: Frame mismatch - expected {expected_frame}, got {actual_frame}")
                return False, actual_frame, {
                    "error_type": "FRAME_SELECTION_MISMATCH",
                    "message": "Frame selection mismatch",
                    "expected_frame": expected_frame,
                    "actual_frame": actual_frame,
                    "recoverable": True,
                    "request_id": self.request_id
                }
            
            self.log(f"{operation}: Frame verified: {actual_frame}")
            return True, actual_frame, None
            
        except Exception as e:
            self.log(f"{operation}: Frame verification failed: {e}")
            return False, None, {
                "error_type": "FRAME_VERIFICATION_ERROR",
                "message": f"Frame verification error: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_keyframe_exists(self, node, doc, frame, operation="create_keyframe"):
        """
        Verify that a keyframe exists at the specified frame.
        
        Returns: (success: bool, exists: bool, error_dict or None)
        """
        try:
            has_method = getattr(node, "hasKeyframeAtTime", None)
            if not callable(has_method):
                self.log(f"{operation}: hasKeyframeAtTime not available")
                return False, False, {
                    "error_type": "KEYFRAME_API_UNAVAILABLE",
                    "message": "Keyframe verification API not available",
                    "recoverable": False,
                    "request_id": self.request_id
                }
            
            exists = bool(has_method(int(frame)))
            self.log(f"{operation}: Keyframe at {frame} exists={exists}")
            return True, exists, None
            
        except Exception as e:
            self.log(f"{operation}: Keyframe verification failed: {e}")
            return False, False, {
                "error_type": "KEYFRAME_VERIFICATION_ERROR",
                "message": f"Keyframe verification error: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_file_created(self, filepath, min_size=100, operation="save_file"):
        """
        Verify that a file was created and has minimum size.
        
        Returns: (success: bool, file_stats or None, error_dict or None)
        """
        import os
        
        try:
            if not os.path.exists(filepath):
                self.log(f"{operation}: File does not exist: {filepath}")
                return False, None, {
                    "error_type": "FILE_NOT_CREATED",
                    "message": f"File was not created: {filepath}",
                    "filepath": filepath,
                    "recoverable": False,
                    "request_id": self.request_id
                }
            
            file_stats = os.stat(filepath)
            file_size = file_stats.st_size
            
            if file_size < min_size:
                self.log(f"{operation}: File too small: {file_size} bytes < {min_size} bytes")
                return False, None, {
                    "error_type": "FILE_TOO_SMALL",
                    "message": f"File created but suspiciously small: {file_size} bytes",
                    "filepath": filepath,
                    "file_size": file_size,
                    "expected_min_size": min_size,
                    "recoverable": False,
                    "request_id": self.request_id
                }
            
            self.log(f"{operation}: File verified: {filepath} ({file_size} bytes)")
            return True, {
                "filepath": filepath,
                "file_size": file_size,
                "exists": True
            }, None
            
        except Exception as e:
            self.log(f"{operation}: File verification failed: {e}")
            return False, None, {
                "error_type": "FILE_VERIFICATION_ERROR",
                "message": f"File verification error: {e}",
                "filepath": filepath,
                "recoverable": False,
                "request_id": self.request_id
            }
    
    def verify_document_in_view(self, app, doc, operation="create_document"):
        """
        Verify that document is actually in the active window view.
        
        Returns: (success: bool, error_dict or None)
        """
        try:
            window = app.activeWindow()
            if not window:
                self.log(f"{operation}: No active window")
                return False, {
                    "error_type": "WINDOW_NOT_FOUND",
                    "message": "No active window to display document",
                    "recoverable": False,
                    "request_id": self.request_id
                }
            
            views = window.views()
            doc_in_views = any(v.document() == doc for v in views)
            
            if not doc_in_views:
                self.log(f"{operation}: Document not in any view")
                return False, {
                    "error_type": "DOCUMENT_NOT_IN_VIEW",
                    "message": "Document created but not visible in window",
                    "recoverable": False,
                    "request_id": self.request_id
                }
            
            self.log(f"{operation}: Document in view verified")
            return True, None
            
        except Exception as e:
            self.log(f"{operation}: Document view verification failed: {e}")
            return False, {
                "error_type": "DOCUMENT_VIEW_VERIFICATION_ERROR",
                "message": f"Document view verification error: {e}",
                "recoverable": False,
                "request_id": self.request_id
            }


# =============================================================================
# ENHANCED COMMAND HANDLERS WITH STATE VERIFICATION
# =============================================================================

# These are the enhanced versions to replace existing handlers in __init__.py

def cmd_select_paint_layer_verified(self, params, request_id=None):
    """
    P0.2: Select active paint layer WITH VERIFICATION.
    
    Fixes critical silent failure where layer selection wasn't verified.
    """
    verifier = StateVerifier(request_id)
    
    doc = self.get_active_document()
    success, error = verifier.verify_document(doc, "select_paint_layer")
    if not success:
        return error
    
    layer = self._ensure_active_paint_layer()
    success, error = verifier.verify_layer(layer, "select_paint_layer")
    if not success:
        return error
    
    # CRITICAL: Set layer as active
    doc.setActiveNode(layer)
    
    # CRITICAL: Verify layer is actually selected
    success, actual_layer, error = verifier.verify_layer_selected(doc, layer, "select_paint_layer")
    if not success:
        return error
    
    return {
        "status": "ok",
        "layer_name": actual_layer.name(),
        "layer_type": actual_layer.type(),
        "verified": True,
        "request_id": request_id
    }


def cmd_set_current_frame_verified(self, params, request_id=None):
    """
    P0.3: Set current frame WITH VERIFICATION.
    
    Fixes critical silent failure where frame selection wasn't verified.
    """
    verifier = StateVerifier(request_id)
    
    doc = self.get_active_document()
    success, error = verifier.verify_document(doc, "set_current_frame")
    if not success:
        return error
    
    frame = int(params.get("frame", 0))
    
    # Set the frame
    try:
        doc.setCurrentTime(frame)
    except Exception as e:
        verifier.log(f"setCurrentTime failed: {e}")
        return {
            "error_type": "FRAME_SELECTION_FAILED",
            "message": f"Failed to set frame: {e}",
            "requested_frame": frame,
            "recoverable": True,
            "request_id": request_id
        }
    
    # CRITICAL: Verify frame is actually selected
    success, actual_frame, error = verifier.verify_frame_selected(doc, frame, "set_current_frame")
    if not success:
        return error
    
    # Get keyframes for context
    node = self._get_active_paint_layer()
    keyframes = self._list_keyframes(node, doc) if node else []
    
    return {
        "status": "ok",
        "current_frame": actual_frame,
        "verified": True,
        "keyframes": keyframes,
        "request_id": request_id
    }


def cmd_create_keyframe_verified(self, params, request_id=None):
    """
    P0.4: Create keyframe WITH RETRY AND VERIFICATION.
    
    Fixes critical known unreliable keyframe creation with:
    - Pre-verification of requirements
    - Retry logic (2 attempts)
    - Post-verification
    - Clear failure reporting
    """
    verifier = StateVerifier(request_id)
    
    doc = self.get_active_document()
    success, error = verifier.verify_document(doc, "create_keyframe")
    if not success:
        return error
    
    node = self._ensure_active_paint_layer()
    success, error = verifier.verify_layer(node, "create_keyframe")
    if not success:
        return error
    
    frame = int(params.get("frame", self._get_current_time(doc)))
    
    # Pre-check: Does keyframe already exist?
    success, exists, error = verifier.verify_keyframe_exists(node, doc, frame, "create_keyframe_precheck")
    if not success:
        return error
    
    if exists:
        verifier.log(f"Keyframe at {frame} already exists")
        return {
            "status": "ok",
            "created_frame": frame,
            "current_frame": self._get_current_time(doc),
            "keyframes": self._list_keyframes(node, doc),
            "already_existed": True,
            "verified": True,
            "request_id": request_id
        }
    
    # Attempt creation with retry
    max_attempts = 2
    for attempt in range(max_attempts):
        verifier.log(f"Keyframe creation attempt {attempt + 1}/{max_attempts}")
        
        created = self._create_keyframe(node, doc, frame)
        
        # CRITICAL: Verify keyframe actually created
        success, exists, error = verifier.verify_keyframe_exists(node, doc, frame, "create_keyframe_verify")
        
        if success and exists:
            verifier.log(f"Keyframe creation verified on attempt {attempt + 1}")
            return {
                "status": "ok",
                "created_frame": frame,
                "current_frame": self._get_current_time(doc),
                "keyframes": self._list_keyframes(node, doc),
                "attempts": attempt + 1,
                "verified": True,
                "request_id": request_id
            }
        
        if attempt < max_attempts - 1:
            verifier.log(f"Keyframe not verified, retrying...")
            # Brief delay for Qt events
            QApplication.processEvents()
    
    # All attempts failed
    verifier.log(f"Keyframe creation failed after {max_attempts} attempts")
    keyframes = self._list_keyframes(node, doc)
    
    return {
        "error_type": "KEYFRAME_CREATION_FAILED",
        "message": f"Failed to create keyframe at frame {frame} after {max_attempts} attempts",
        "requested_frame": frame,
        "current_frame": self._get_current_time(doc),
        "keyframes": keyframes,
        "attempts": max_attempts,
        "recoverable": True,
        "debug": self._diagnose_timeline(doc),
        "request_id": request_id,
        "known_limitation": "Krita keyframe API has known reliability issues"
    }


def cmd_new_canvas_verified(self, params, request_id=None):
    """
    P0.5: Create new canvas WITH VERIFICATION.
    
    Fixes critical silent failures where document/layer creation wasn't verified.
    """
    verifier = StateVerifier(request_id)
    
    width = params.get("width", 800)
    height = params.get("height", 600)
    name = params.get("name", "New Canvas")
    bg_color = params.get("background", "#1a1a2e")
    
    # Validate dimensions
    if width < 1 or width > 10000:
        return {
            "error_type": "INVALID_DIMENSIONS",
            "message": f"Invalid width: {width} (must be 1-10000)",
            "recoverable": True,
            "request_id": request_id
        }
    
    if height < 1 or height > 10000:
        return {
            "error_type": "INVALID_DIMENSIONS",
            "message": f"Invalid height: {height} (must be 1-10000)",
            "recoverable": True,
            "request_id": request_id
        }
    
    app = Krita.instance()
    
    # Create document
    try:
        doc = app.createDocument(width, height, name, "RGBA", "U8", "", 120.0)
    except Exception as e:
        verifier.log(f"createDocument failed: {e}")
        return {
            "error_type": "DOCUMENT_CREATION_FAILED",
            "message": f"Failed to create document: {e}",
            "recoverable": False,
            "request_id": request_id
        }
    
    # Verify document created
    success, error = verifier.verify_document(doc, "new_canvas")
    if not success:
        return error
    
    # Add to window
    window = app.activeWindow()
    if window:
        try:
            window.addView(doc)
        except Exception as e:
            verifier.log(f"addView failed: {e}")
            return {
                "error_type": "VIEW_CREATION_FAILED",
                "message": f"Failed to add view: {e}",
                "recoverable": False,
                "request_id": request_id
            }
    
    # CRITICAL: Verify document in view
    success, error = verifier.verify_document_in_view(app, doc, "new_canvas")
    if not success:
        return error
    
    # Create a paint layer
    root = doc.rootNode()
    layer = doc.createNode("paint", "paintlayer")
    root.addChildNode(layer, None)
    doc.setActiveNode(layer)
    
    # CRITICAL: Verify layer created and selected
    success, actual_layer, error = verifier.verify_layer_selected(doc, layer, "new_canvas")
    if not success:
        return error
    
    # Fill background using pixel data
    color = QColor(bg_color)
    r, g, b = color.red(), color.green(), color.blue()
    pixel_data = bytes([b, g, r, 255] * (width * height))
    layer.setPixelData(pixel_data, 0, 0, width, height)
    doc.refreshProjection()
    
    # Verify dimensions
    actual_width = doc.width()
    actual_height = doc.height()
    
    if actual_width != width or actual_height != height:
        verifier.log(f"Dimension mismatch: requested {width}x{height}, got {actual_width}x{actual_height}")
        return {
            "error_type": "DIMENSION_MISMATCH",
            "message": "Document dimensions don't match requested",
            "requested_width": width,
            "requested_height": height,
            "actual_width": actual_width,
            "actual_height": actual_height,
            "recoverable": False,
            "request_id": request_id
        }
    
    return {
        "status": "ok",
        "width": actual_width,
        "height": actual_height,
        "name": name,
        "layer_name": actual_layer.name(),
        "verified": True,
        "request_id": request_id
    }


def cmd_save_verified(self, params, request_id=None):
    """
    P0.6: Save file WITH VERIFICATION.
    
    Fixes critical silent failure where file creation wasn't verified.
    """
    verifier = StateVerifier(request_id)
    
    filepath = params.get("path")
    if not filepath:
        return {
            "error_type": "INVALID_PARAMETER",
            "message": "No path specified",
            "recoverable": True,
            "request_id": request_id
        }
    
    doc = self.get_active_document()
    success, error = verifier.verify_document(doc, "save")
    if not success:
        return error
    
    # Ensure parent directory exists
    import os
    parent_dir = os.path.dirname(filepath)
    if parent_dir and not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir, exist_ok=True)
        except Exception as e:
            verifier.log(f"Failed to create directory: {e}")
            return {
                "error_type": "DIRECTORY_CREATION_FAILED",
                "message": f"Failed to create directory: {e}",
                "filepath": filepath,
                "recoverable": False,
                "request_id": request_id
            }
    
    # Perform save
    try:
        doc.setBatchmode(True)
        doc.exportImage(filepath, InfoObject())
        doc.setBatchmode(False)
    except Exception as e:
        verifier.log(f"exportImage failed: {e}")
        return {
            "error_type": "SAVE_FAILED",
            "message": f"Failed to save file: {e}",
            "filepath": filepath,
            "recoverable": False,
            "request_id": request_id
        }
    
    # CRITICAL: Verify file created
    success, file_stats, error = verifier.verify_file_created(filepath, min_size=100, operation="save")
    if not success:
        return error
    
    return {
        "status": "ok",
        "path": filepath,
        "file_size": file_stats["file_size"],
        "verified": True,
        "request_id": request_id
    }


def cmd_get_canvas_verified(self, params, request_id=None):
    """
    P0.6: Export canvas WITH VERIFICATION.
    
    Fixes critical silent failure where export wasn't verified.
    """
    verifier = StateVerifier(request_id)
    
    filename = params.get("filename", "canvas.png")
    
    doc = self.get_active_document()
    success, error = verifier.verify_document(doc, "get_canvas")
    if not success:
        return error
    
    # Ensure filename has extension
    if not filename.endswith('.png'):
        filename += '.png'
    
    filepath = os.path.join(CANVAS_OUTPUT_DIR, filename)
    
    # Ensure output directory exists
    os.makedirs(CANVAS_OUTPUT_DIR, exist_ok=True)
    
    # Export image
    try:
        doc.setBatchmode(True)
        doc.exportImage(filepath, InfoObject())
        doc.setBatchmode(False)
    except Exception as e:
        verifier.log(f"exportImage failed: {e}")
        return {
            "error_type": "EXPORT_FAILED",
            "message": f"Failed to export canvas: {e}",
            "filepath": filepath,
            "recoverable": False,
            "request_id": request_id
        }
    
    # CRITICAL: Verify file created
    success, file_stats, error = verifier.verify_file_created(filepath, min_size=100, operation="get_canvas")
    if not success:
        return error
    
    return {
        "status": "ok",
        "path": filepath,
        "filename": filename,
        "file_size": file_stats["file_size"],
        "verified": True,
        "request_id": request_id
    }

