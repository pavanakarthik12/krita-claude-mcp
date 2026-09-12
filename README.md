# Krita MCP Server

**✅ Status: Claude Desktop Ready** | [Setup Guide](CLAUDE_DESKTOP_SETUP.md) | [Implementation Report](IMPLEMENTATION_REPORT.md)

> **Latest Update (Aug 26, 2026):** All stdout pollution eliminated, structured returns implemented, comprehensive error handling added. Ready for production Claude Desktop integration.

Let AI paint in [Krita](https://krita.org/) via the [Model Context Protocol](https://modelcontextprotocol.io/).

This bridge allows Claude (or any MCP client) to create canvases, paint strokes, draw shapes, export images, and more — all inside a running Krita instance.

## How It Works

Two components:

1. **Krita Plugin** (`krita-plugin/`) — A Python plugin that runs inside Krita, exposing an HTTP server on `localhost:5678`. It receives paint commands and executes them on Krita's main thread via a command queue.

2. **MCP Server** (`server.py`) — A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes painting tools to any MCP client. It translates MCP tool calls into HTTP requests to the Krita plugin.

```
MCP Client (Claude, etc.)  ←→  MCP Server (server.py)  ←→  Krita Plugin (HTTP on :5678)  ←→  Krita
```

## Setup

### 1. Install the Krita Plugin

Copy the plugin files to your Krita plugins directory:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\krita\pykrita\` |
| Linux | `~/.local/share/krita/pykrita/` |
| macOS | `~/Library/Application Support/krita/pykrita/` |

Copy both:
- `krita-plugin/kritamcp/` (the folder with `__init__.py`)
- `krita-plugin/kritamcp.desktop`

Then in Krita: **Settings → Configure Krita → Python Plugin Manager → Enable "Krita MCP Bridge"** and restart Krita.

### 2. Install the MCP Server

```bash
pip install fastmcp httpx
```

Or with a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 3. Configure Your MCP Client

Add to your MCP client config (e.g., Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "krita": {
      "command": "python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

If using a virtual environment:
```json
{
  "mcpServers": {
    "krita": {
      "command": "/path/to/.venv/Scripts/python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

## Available Tools

### Inspection & Information (Read-Only)
| Tool | Description |
|------|-------------|
| `krita_health` | Check if Krita is running with the plugin active |
| `krita_list_layers` | **NEW** List all layers with hierarchy, visibility, opacity, and active status |
| `krita_get_canvas_info` | **NEW** Get canvas dimensions, color mode, current frame, animation metadata |
| `krita_get_color_at` | Eyedropper — sample color at a pixel |
| `krita_list_brushes` | List available brush presets |

### Document Management
| Tool | Description |
|------|-------------|
| `krita_new_canvas` | Create a new canvas (width, height, background color) |
| `krita_open_file` | Open an existing .kra, .png, .jpg, etc. |
| `krita_save` | Save canvas to a specific file path |
| `krita_get_canvas` | Export canvas to PNG (for AI to see progress) |

### Drawing & Painting
| Tool | Description |
|------|-------------|
| `krita_set_color` | Set foreground paint color (hex) |
| `krita_set_brush` | Set brush preset, size, and opacity |
| `krita_stroke` | Paint a stroke through a list of [x, y] points |
| `krita_fill` | Fill a circular area at a point |
| `krita_draw_shape` | Draw rectangle, ellipse, or line |
| `krita_bulk_strokes` | Paint multiple strokes in one operation (high performance) |

### Editing
| Tool | Description |
|------|-------------|
| `krita_undo` / `krita_redo` | Undo/redo actions |
| `krita_clear` | Clear canvas to a solid color |

### Animation (27 tools total)
| Tool | Description |
|------|-------------|
| `krita_select_paint_layer` | Select the active paint layer for drawing |
| `krita_get_current_frame` | Get current timeline frame and keyframes |
| `krita_set_current_frame` | Set current timeline frame (move playhead) |
| `krita_create_keyframe` | Create an animation keyframe |
| `krita_delete_keyframe` | Delete a keyframe |
| `krita_list_keyframes` | List all keyframes on active layer |
| `krita_has_keyframe` | Check if keyframe exists at frame |
| `krita_enable_onion` | Enable/disable onion skin preview |
| `krita_inspect_previous_frame` | Get downsampled color grid of previous frame |

## The Export Timeout Fix

**This is the main reason this repo exists.**

By default, HTTP requests and command queue operations time out after ~30 seconds. Canvas export (`get_canvas`) and file save (`save`) operations can easily exceed this on larger canvases, causing silent failures or timeout errors.

The fix is applied in two places:

**MCP Server (`server.py`)** — Extended timeout for export/save commands:
```python
# In krita_get_canvas and krita_save:
result = send_command("get_canvas", {"filename": filename}, timeout=120.0)
result = send_command("save", {"path": path}, timeout=120.0)
```

**Krita Plugin (`__init__.py`)** — Matching timeout in the command queue:
```python
def get_result(self, command_id, timeout=120):
    """Wait for result with timeout."""
    for _ in range(int(timeout * 10)):  # Check every 100ms
        ...
```

**Both sides must match.** If only the MCP server timeout is increased, the plugin's command queue will still time out at 30s. If only the plugin timeout is increased, the HTTP request from the MCP server will time out first.

## Configuration

| Setting | Default | How to Change |
|---------|---------|---------------|
| Plugin HTTP port | `5678` | Edit `SERVER_PORT` in plugin `__init__.py` |
| MCP server URL | `http://localhost:5678` | Set `KRITA_URL` env var |
| Canvas output dir | `~/krita-mcp-output` | Edit `CANVAS_OUTPUT_DIR` in plugin `__init__.py` |

## Usage Examples

### Inspecting Layer Structure

```python
# List all layers in the document
result = krita_list_layers()

# Example output:
{
  "success": True,
  "layers": [
    {
      "name": "Background",
      "type": "paintlayer",
      "visible": True,
      "opacity": 255,
      "is_active": False,
      "depth": 0,
      "parent": None
    },
    {
      "name": "Character Group",
      "type": "grouplayer",
      "visible": True,
      "opacity": 255,
      "is_active": False,
      "depth": 0,
      "children": [
        {
          "name": "Body",
          "type": "paintlayer",
          "visible": True,
          "opacity": 255,
          "is_active": True,
          "depth": 1,
          "parent": "Character Group"
        }
      ]
    }
  ],
  "layer_count": 2
}
```

### Getting Canvas Information

```python
# Get canvas dimensions and metadata
result = krita_get_canvas_info()

# Example output:
{
  "success": True,
  "width": 1920,
  "height": 1080,
  "name": "My Animation",
  "color_model": "RGBA",
  "color_depth": "U8",
  "current_frame": 5,
  "animation_length": 24,
  "frame_rate": 12,
  "active_layer": {
    "name": "Paint Layer",
    "type": "paintlayer"
  }
}
```

### Claude Desktop Usage

When using through Claude Desktop, you can ask:

- **"List all layers in my Krita document"** → Uses `krita_list_layers`
- **"What are the canvas dimensions?"** → Uses `krita_get_canvas_info`
- **"Which layer is currently active?"** → Uses `krita_list_layers` or `krita_get_canvas_info`
- **"What frame am I on?"** → Uses `krita_get_canvas_info`
- **"Show me the layer hierarchy"** → Uses `krita_list_layers`

These inspection tools are **strictly read-only** and will never modify your document, change layers, or move the timeline.

## Painting Approach

The plugin paints using **direct pixel manipulation** (not Krita's native brush engine for strokes). This means:

- Strokes use a custom soft-circle renderer with configurable hardness
- Alpha blending is done manually in BGRA pixel format
- Shapes (rectangle, ellipse, line) are rasterized directly
- This approach is reliable and doesn't depend on Krita's internal brush state

The `set_brush` tool does set Krita's brush preset (for potential future use), but `stroke` currently uses its own pixel-level rendering.

## License

MIT
