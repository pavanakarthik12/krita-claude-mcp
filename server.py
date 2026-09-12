"""
Krita MCP Server - Claude Desktop Ready
Bridge between Claude and Krita painting application.

Uses FastMCP to expose Krita painting tools over the Model Context Protocol,
communicating with a Krita plugin via HTTP.

Architecture:
    Claude Desktop -> MCP stdio -> server.py -> HTTP -> Krita plugin -> Krita
"""

from fastmcp import FastMCP
import httpx
import os
import sys
import uuid
from typing import Optional, Union

# Configuration
KRITA_URL = os.environ.get("KRITA_URL", "http://localhost:5678")

mcp = FastMCP("krita-mcp")

# Logging to stderr to avoid corrupting stdio MCP communication
def log(message: str):
    """Log to stderr to avoid polluting stdout MCP channel."""
    print(f"[Krita MCP] {message}", file=sys.stderr, flush=True)


def send_command(action: str, params: dict = None, timeout: float = 30.0, request_id: str = None) -> dict:
    """Send command to Krita plugin and return result."""
    if params is None:
        params = {}
    
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]

    try:
        response = httpx.post(
            KRITA_URL,
            json={"action": action, "params": params, "request_id": request_id},
            timeout=timeout
        )
        result = response.json()
        # Ensure request_id in response
        if "request_id" not in result:
            result["request_id"] = request_id
        return result
    except httpx.ConnectError:
        return {
            "success": False,
            "error": {
                "type": "connection_error",
                "message": "Cannot connect to Krita. Is Krita running with the MCP plugin enabled?",
                "recoverable": True
            },
            "request_id": request_id
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": {
                "type": "timeout",
                "message": f"Operation timed out after {timeout}s",
                "recoverable": False
            },
            "request_id": request_id
        }
    except ValueError as e:
        return {
            "success": False,
            "error": {
                "type": "invalid_plugin_response",
                "message": f"Krita returned invalid JSON: {e}",
                "recoverable": True
            },
            "request_id": request_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": {
                "type": "unknown",
                "message": str(e),
                "recoverable": False
            },
            "request_id": request_id
        }


# ==============================================================================
# UTILITY TOOLS
# ==============================================================================

@mcp.tool()
def krita_health() -> dict:
    """
    Check if Krita is running and the MCP plugin is active.
    
    Returns connection status and plugin information.
    Use this first to verify Krita is ready.
    """
    try:
        response = httpx.get(f"{KRITA_URL}/health", timeout=5.0)
        data = response.json()
        return {
            "success": True,
            "connected": True,
            "plugin": data.get("plugin", "unknown"),
            "url": KRITA_URL
        }
    except:
        return {
            "success": False,
            "connected": False,
            "error": {
                "type": "connection_error",
                "message": "Cannot connect to Krita. Make sure Krita is running with the MCP plugin enabled.",
                "recoverable": True
            }
        }


@mcp.tool()
def krita_list_brushes(filter: str = "", limit: int = 20) -> dict:
    """
    List available brush presets in Krita.

    Args:
        filter: Filter brushes by name (partial match)
        limit: Maximum number to return (default 20)
        
    Returns list of available brush preset names.
    """
    result = send_command("list_brushes", {"filter": filter, "limit": limit})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "brushes": result.get("brushes", []),
        "count": result.get("count", 0)
    }


@mcp.tool()
def krita_list_layers() -> dict:
    """
    List all layers in the current Krita document (READ-ONLY).
    
    Returns structured information about every layer including:
    - Layer name and type (paintlayer, grouplayer, etc.)
    - Visibility and opacity
    - Layer hierarchy (parent/child relationships)
    - Which layer is currently active
    - Layer UUIDs for identification
    - Animation status if applicable
    
    This is strictly read-only and does not select, modify, or otherwise
    change any layer state. Use this to inspect the layer structure before
    making decisions about which layers to work with.
    
    Returns empty list if no document is open.
    """
    result = send_command("list_layers", {})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "list_layers",
        "layers": result.get("layers", []),
        "layer_count": result.get("layer_count", 0),
        "active_layer_uuid": result.get("active_layer_uuid")
    }


@mcp.tool()
def krita_get_canvas_info() -> dict:
    """
    Get canvas and document metadata (READ-ONLY).
    
    Returns comprehensive information about the current document:
    - Canvas dimensions (width and height in pixels)
    - Color model and bit depth
    - Document name and filename
    - Resolution (DPI)
    - Current frame/time for animations
    - Animation length and frame rate
    - Playback range
    - Active layer information
    - Document modification state
    
    This is strictly read-only and does not change any document state.
    Use this to understand the canvas you're working with.
    
    Returns error if no document is open.
    """
    result = send_command("get_canvas_info", {})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "get_canvas_info",
        "width": result.get("width"),
        "height": result.get("height"),
        "name": result.get("name"),
        "filename": result.get("filename"),
        "resolution": result.get("resolution"),
        "color_model": result.get("color_model"),
        "color_depth": result.get("color_depth"),
        "color_profile": result.get("color_profile"),
        "current_frame": result.get("current_frame"),
        "animation_length": result.get("animation_length"),
        "playback_start": result.get("playback_start"),
        "playback_end": result.get("playback_end"),
        "frame_rate": result.get("frame_rate"),
        "active_layer": result.get("active_layer"),
        "modified": result.get("modified")
    }


# ==============================================================================
# DOCUMENT MANAGEMENT
# ==============================================================================

@mcp.tool()
def krita_new_canvas(
    width: int = 800,
    height: int = 600,
    name: str = "New Canvas",
    background: str = "#1a1a2e"
) -> dict:
    """
    Create a new canvas in Krita.

    Args:
        width: Canvas width in pixels (default 800)
        height: Canvas height in pixels (default 600)
        name: Document name
        background: Background color as hex (default dark blue #1a1a2e)
        
    Creates a new document with a paint layer ready for drawing.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_new_canvas[{request_id}]: {width}x{height}")
    
    result = send_command("new_canvas", {
        "width": width,
        "height": height,
        "name": name,
        "background": background
    }, request_id=request_id)

    if "error" in result or "error_type" in result:
        return result
    
    return {
        "success": True,
        "operation": "create_canvas",
        "width": width,
        "height": height,
        "name": name,
        "background": background,
        "verified": result.get("verified", False),
        "request_id": request_id
    }


@mcp.tool()
def krita_open_file(path: str) -> dict:
    """
    Open an existing file in Krita (.kra, .png, .jpg, etc).

    Args:
        path: Full file path to open
        
    Opens the file and adds it to the active window.
    """
    result = send_command("open_file", {"path": path}, timeout=30.0)

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "open_file",
        "path": path,
        "name": result.get("name", "unknown"),
        "width": result.get("width", 0),
        "height": result.get("height", 0)
    }


@mcp.tool()
def krita_save(path: str) -> dict:
    """
    Save the current canvas to a specific file path.

    Args:
        path: Full file path to save to (e.g., "C:/art/my_painting.png")
        
    Supports .png, .jpg, .kra and other Krita formats.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_save[{request_id}]: {path}")
    
    result = send_command("save", {"path": path}, timeout=120.0, request_id=request_id)

    if "error" in result or "error_type" in result:
        return result
    
    return {
        "success": True,
        "operation": "save",
        "path": path,
        "file_size": result.get("file_size"),
        "verified": result.get("verified", False),
        "request_id": request_id
    }


@mcp.tool()
def krita_get_canvas(filename: str = "canvas.png") -> dict:
    """
    Export current canvas to a PNG file for inspection.
    
    Args:
        filename: Output filename (saved to ~/krita-mcp-output/)
        
    Returns the full file path. Use this to inspect what you've drawn.
    Claude can then analyze the exported image.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_get_canvas[{request_id}]: {filename}")
    
    result = send_command("get_canvas", {"filename": filename}, timeout=120.0, request_id=request_id)

    if "error" in result or "error_type" in result:
        return result
    
    return {
        "success": True,
        "operation": "export_canvas",
        "path": result.get("path", ""),
        "filename": filename,
        "file_size": result.get("file_size"),
        "verified": result.get("verified", False),
        "request_id": request_id
    }


# ==============================================================================
# DRAWING TOOLS
# ==============================================================================

@mcp.tool()
def krita_set_color(color: str) -> dict:
    """
    Set the foreground (paint) color.

    Args:
        color: Hex color code (e.g., "#ff0000" for red, "#00ff00" for green)
        
    Sets the color used for subsequent drawing operations.
    """
    result = send_command("set_color", {"color": color})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "set_color",
        "color": color
    }


@mcp.tool()
def krita_set_brush(
    preset: Optional[str] = None,
    size: Optional[int] = None,
    opacity: Optional[float] = None
) -> dict:
    """
    Set brush preset and properties.

    Args:
        preset: Brush preset name (partial match, e.g., "Basic", "Soft")
        size: Brush size in pixels
        opacity: Brush opacity (0.0 to 1.0)
        
    Configure brush settings for drawing operations.
    """
    params = {}
    if preset:
        params["preset"] = preset
    if size:
        params["size"] = size
    if opacity is not None:
        params["opacity"] = opacity

    result = send_command("set_brush", params)

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "set_brush",
        "preset": preset,
        "size": size,
        "opacity": opacity
    }


@mcp.tool()
def krita_stroke(points: list[list[int]], pressure: float = 1.0) -> dict:
    """
    Paint a stroke through a series of points.

    Args:
        points: List of [x, y] coordinate pairs, e.g., [[100, 100], [150, 120]]
        pressure: Brush pressure (0.0 to 1.0, affects thickness/opacity)
        
    Draws a smooth stroke connecting the points with current color/brush.
    For multiple strokes, use krita_bulk_strokes for better performance.
    """
    if len(points) < 2:
        return {
            "success": False,
            "error": {
                "type": "invalid_parameters",
                "message": "Need at least 2 points for a stroke",
                "recoverable": True
            }
        }

    result = send_command("stroke", {
        "points": points,
        "pressure": pressure
    })

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "stroke",
        "points_count": len(points),
        "pressure": pressure
    }


@mcp.tool()
def krita_fill(x: int, y: int, radius: int = 50) -> dict:
    """
    Fill a circular area with current color.

    Args:
        x: X coordinate of center
        y: Y coordinate of center
        radius: Fill radius in pixels (default 50)
        
    Paints a filled circle at the specified location.
    """
    result = send_command("fill", {"x": x, "y": y, "radius": radius})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "fill",
        "x": x,
        "y": y,
        "radius": radius
    }


@mcp.tool()
def krita_draw_shape(
    shape: str,
    x: int,
    y: int,
    width: int = 100,
    height: int = 100,
    fill: bool = True,
    stroke: bool = False,
    x2: Optional[int] = None,
    y2: Optional[int] = None
) -> dict:
    """
    Draw a shape on the canvas.

    Args:
        shape: Type of shape - "rectangle", "ellipse", or "line"
        x: X coordinate (top-left for shapes, start point for lines)
        y: Y coordinate (top-left for shapes, start point for lines)
        width: Width of shape (ignored for lines if x2/y2 provided)
        height: Height of shape (ignored for lines if x2/y2 provided)
        fill: Whether to fill the shape
        stroke: Whether to draw outline
        x2: End X for lines (optional)
        y2: End Y for lines (optional)
        
    Draws geometric shapes with current color.
    """
    params = {
        "shape": shape,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "fill": fill,
        "stroke": stroke
    }
    if x2 is not None:
        params["x2"] = x2
    if y2 is not None:
        params["y2"] = y2

    result = send_command("draw_shape", params)

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "draw_shape",
        "shape": shape,
        "x": x,
        "y": y
    }


@mcp.tool()
def krita_draw_path(
    segments: list[dict],
    color: Optional[str] = None,
    brush_size: int = 20,
    opacity: float = 1.0,
    hardness: float = 0.5,
    samples_per_segment: int = 24
) -> dict:
    """Draw connected cubic Bezier segments as one deterministic path.

    Each segment must contain ``start``, ``control1``, ``control2``, and
    ``end`` points, each represented as ``[x, y]``.
    """
    params = {
        "segments": segments,
        "brush_size": brush_size,
        "opacity": opacity,
        "hardness": hardness,
        "samples_per_segment": samples_per_segment
    }
    if color is not None:
        params["color"] = color

    result = send_command("draw_path", params, timeout=120.0)

    if "error" in result:
        return result

    return {
        "success": result.get("status") == "ok",
        "operation": "draw_path",
        "segments_drawn": result.get("segments_drawn", 0),
        "points_sampled": result.get("points_sampled", 0),
        "errors": result.get("errors")
    }


@mcp.tool()
def krita_bulk_strokes(strokes: list[dict]) -> dict:
    """
    Draw multiple strokes in one operation. CRITICAL for animation performance.
    
    This significantly reduces communication overhead by batching multiple stroke
    operations into a single MCP call. Each stroke can have its own color, brush
    size, and other properties.
    
    Args:
        strokes: List of stroke specifications, each containing:
            - points: List of [x, y] coordinate pairs (required)
            - color: Hex color code (optional, e.g., "#ff0000")
            - brush_size: Brush size in pixels (optional)
            - pressure: Brush pressure 0.0-1.0 (optional, default 1.0)
            - hardness: Brush hardness 0.0-1.0 (optional, default 0.5)
            - opacity: Stroke opacity 0.0-1.0 (optional, default 1.0)
    
    Returns:
        Dictionary with operation results including strokes_drawn, strokes_failed
    
    Example:
        krita_bulk_strokes([
            {
                "points": [[100, 100], [150, 150]],
                "color": "#ff0000",
                "brush_size": 5
            },
            {
                "points": [[200, 200], [250, 250]],
                "color": "#00ff00",
                "brush_size": 3
            }
        ])
        
    Use this instead of multiple krita_stroke calls for better performance.
    """
    log(f"[bulk_strokes] Processing {len(strokes)} strokes")
    
    # Extended timeout for bulk operations
    timeout = max(120.0, len(strokes) * 0.5)
    
    result = send_command("bulk_strokes", {"strokes": strokes}, timeout=timeout)
    
    if "error" in result:
        log(f"[bulk_strokes] Error: {result['error']}")
        return result
    
    log(f"[bulk_strokes] Success: {result.get('strokes_drawn', 0)} strokes drawn")
    
    return {
        "success": result.get("status") == "ok",
        "operation": "bulk_strokes",
        "strokes_drawn": result.get("strokes_drawn", 0),
        "strokes_failed": result.get("strokes_failed", 0),
        "total_strokes": result.get("total_strokes", len(strokes)),
        "errors": result.get("errors")
    }


# ==============================================================================
# EDITING TOOLS
# ==============================================================================

@mcp.tool()
def krita_undo() -> dict:
    """Undo the last action."""
    result = send_command("undo", {})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "undo"
    }


@mcp.tool()
def krita_redo() -> dict:
    """Redo the last undone action."""
    result = send_command("redo", {})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "redo"
    }


@mcp.tool()
def krita_clear(color: str = "#1a1a2e") -> dict:
    """
    Clear the canvas to a solid color.

    Args:
        color: Color to fill canvas with (default dark blue)
        
    Erases all content and fills with the specified color.
    """
    result = send_command("clear", {"color": color})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "clear",
        "color": color
    }


@mcp.tool()
def krita_get_color_at(x: int, y: int) -> dict:
    """
    Sample the color at a specific pixel (eyedropper).

    Args:
        x: X coordinate
        y: Y coordinate
        
    Returns the color at that pixel in hex and RGB format.
    """
    result = send_command("get_color_at", {"x": x, "y": y})

    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "get_color",
        "x": x,
        "y": y,
        "color": result.get("color", "#000000"),
        "r": result.get("r", 0),
        "g": result.get("g", 0),
        "b": result.get("b", 0)
    }


# ==============================================================================
# ANIMATION TOOLS
# ==============================================================================

@mcp.tool()
def krita_select_paint_layer() -> dict:
    """
    Select the active paint layer for drawing and animation operations.
    
    Call this before animation operations to ensure you're drawing on the correct layer.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_select_paint_layer[{request_id}]")
    
    result = send_command("select_paint_layer", {}, request_id=request_id)
    
    if "error" in result or "error_type" in result:
        return result
    
    return {
        "success": True,
        "operation": "select_paint_layer",
        "layer_name": result.get("layer_name", "unknown"),
        "layer_type": result.get("layer_type", "unknown"),
        "verified": result.get("verified", False),
        "request_id": request_id
    }


@mcp.tool()
def krita_get_current_frame() -> dict:
    """
    Get the current timeline frame and list of keyframes.
    
    Returns the playhead position and all existing keyframes on the active layer.
    Use this to check animation state.
    """
    result = send_command("get_current_frame", {})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "get_current_frame",
        "current_frame": result.get("current_frame", 0),
        "keyframes": result.get("keyframes", [])
    }


@mcp.tool()
def krita_set_current_frame(frame: int) -> dict:
    """
    Set the current timeline frame (move playhead).

    Args:
        frame: Frame number to jump to
        
    Changes which frame you're viewing/editing. Use before drawing on a frame.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_set_current_frame[{request_id}]: frame={frame}")
    
    result = send_command("set_current_frame", {"frame": frame}, request_id=request_id)
    
    if "error" in result or "error_type" in result:
        return result
    
    return {
        "success": True,
        "operation": "set_current_frame",
        "frame": frame,
        "current_frame": result.get("current_frame", frame),
        "keyframes": result.get("keyframes", []),
        "verified": result.get("verified", False),
        "request_id": request_id
    }


@mcp.tool()
def krita_create_keyframe(frame: int) -> dict:
    """
    Create a real animation keyframe on the active paint layer.
    
    Args:
        frame: Frame number to create keyframe at
        
    Creates a blank keyframe ready for drawing. 
    WARNING: This operation can be unreliable due to Krita API limitations.
    Always verify with krita_list_keyframes after creation.
    """
    request_id = str(uuid.uuid4())[:8]
    log(f"krita_create_keyframe[{request_id}]: frame={frame}")
    
    result = send_command("create_keyframe", {"frame": frame}, request_id=request_id)
    
    if "error" in result or "error_type" in result:
        # Include diagnostic info in error
        return {
            "success": False,
            "error": result.get("error") or result.get("message", "Unknown error"),
            "error_type": result.get("error_type", "keyframe_creation_failed"),
            "requested_frame": frame,
            "debug": result.get("debug"),
            "attempts": result.get("attempts"),
            "known_limitation": result.get("known_limitation"),
            "recoverable": result.get("recoverable", True),
            "request_id": request_id
        }
    
    return {
        "success": True,
        "operation": "create_keyframe",
        "frame": frame,
        "created_frame": result.get("created_frame", frame),
        "current_frame": result.get("current_frame", frame),
        "keyframes": result.get("keyframes", []),
        "attempts": result.get("attempts", 1),
        "already_existed": result.get("already_existed", False),
        "verified": result.get("verified", False),
        "request_id": request_id
    }


@mcp.tool()
def krita_delete_keyframe(frame: int) -> dict:
    """
    Delete an animation keyframe on the active paint layer.
    
    Args:
        frame: Frame number to delete
        
    Removes the keyframe at the specified frame.
    """
    result = send_command("delete_keyframe", {"frame": frame})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "delete_keyframe",
        "deleted_frame": result.get("deleted_frame", frame),
        "keyframes": result.get("keyframes", [])
    }


@mcp.tool()
def krita_list_keyframes() -> dict:
    """
    List all keyframes on the active paint layer.
    
    Returns the current frame and all existing keyframes.
    Use this to verify animation structure.
    """
    result = send_command("list_keyframes", {})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "list_keyframes",
        "current_frame": result.get("current_frame", 0),
        "keyframes": result.get("keyframes", []),
        "keyframe_count": len(result.get("keyframes", []))
    }


@mcp.tool()
def krita_has_keyframe(frame: int) -> dict:
    """
    Check whether a keyframe exists at a specific frame.
    
    Args:
        frame: Frame number to check
        
    Returns whether a keyframe exists at that frame.
    """
    result = send_command("has_keyframe", {"frame": frame})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "has_keyframe",
        "frame": frame,
        "exists": result.get("exists", False),
        "keyframes": result.get("keyframes", [])
    }


@mcp.tool()
def krita_enable_onion(enabled: bool = True) -> dict:
    """
    Enable or disable onion skin preview.
    
    Args:
        enabled: True to enable, False to disable
        
    Onion skin shows previous/next frames as semi-transparent overlays.
    Useful for animation continuity.
    """
    result = send_command("enable_onion", {"enabled": enabled})
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "enable_onion",
        "enabled": enabled
    }


@mcp.tool()
def krita_inspect_previous_frame(downscale: int = 32) -> dict:
    """
    Get a downsampled color grid of the previous frame for reference.
    
    Args:
        downscale: Downsampling factor (32 = 32x32 grid)
        
    Returns a 2D array of hex colors representing the previous frame.
    Useful for checking continuity between frames.
    """
    result = send_command("inspect_previous_frame", {"downscale": downscale}, timeout=120.0)
    
    if "error" in result:
        return result
    
    return {
        "success": True,
        "operation": "inspect_previous_frame",
        "grid": result.get("grid", []),
        "downscale": downscale
    }


# ==============================================================================
# COMPATIBILITY WRAPPERS (Legacy tool names)
# ==============================================================================

@mcp.tool()
def krita_create_frame(frame: Optional[int] = None) -> dict:
    """
    Compatibility wrapper: create a keyframe.
    Use krita_create_keyframe instead.
    """
    if frame is None:
        # Get current frame first
        current = send_command("get_current_frame", {})
        frame = current.get("current_frame", 0)
    
    return krita_create_keyframe(frame)


@mcp.tool()
def krita_select_frame(index: int) -> dict:
    """
    Compatibility wrapper: set current frame.
    Use krita_set_current_frame instead.
    """
    return krita_set_current_frame(index)


# ==============================================================================
# SERVER STARTUP
# ==============================================================================

if __name__ == "__main__":
    log("Starting krita-mcp server...")
    log(f"Krita URL: {KRITA_URL}")
    log("Ready for MCP connections via stdio")
    log("Claude will discover tools via MCP protocol")
    
    # Start FastMCP stdio server
    # This will handle all MCP protocol communication
    mcp.run()
