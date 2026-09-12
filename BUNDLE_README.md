# Krita MCP Claude Extension

Deterministic Krita execution tools for Claude Desktop.

## What This Extension Does

This extension allows Claude to control Krita painting application through the Model Context Protocol (MCP). Claude can:

- Create and manage canvases
- Paint strokes and draw shapes
- Manage colors and brushes
- Create and manage animation keyframes
- Export and inspect artwork

**Important**: This extension provides the execution layer only. Claude provides the intelligence and artistic direction.

## Prerequisites

### 1. Krita Must Be Running

This extension communicates with Krita via a plugin. You must:

1. Install Krita (https://krita.org/)
2. Install the **Krita MCP Bridge plugin** (see instructions below)
3. Keep Krita running while using this extension with Claude

### 2. Install Krita MCP Bridge Plugin

**Plugin Location:**
The plugin is located in the original repository:
`krita-plugin/kritamcp/` folder and `kritamcp.desktop` file

**Installation Steps:**

1. Find your Krita resources directory:
   - Open Krita
   - Go to **Settings → Manage Resources → Open Resource Folder**
   - Navigate to the `pykrita/` folder

2. Copy the plugin files:
   - Copy the entire `kritamcp` folder (containing `__init__.py`)
   - Copy the `kritamcp.desktop` file
   - Both should be in the `pykrita/` folder

3. Enable the plugin:
   - In Krita: **Settings → Configure Krita → Python Plugin Manager**
   - Check **"Krita MCP Bridge"**
   - Click **OK**
   - **Restart Krita**

4. Verify the plugin is running:
   - The plugin starts an HTTP server on `http://localhost:5678`
   - You can test it by visiting that URL in a browser

**Plugin Not Included In Bundle:**
The Krita plugin is NOT included in this MCPB bundle because it must be installed directly into Krita. Download the full project from the repository to access the plugin files.

## Configuration

After installing the extension in Claude Desktop, you can configure:

- **Krita Plugin URL**: Default is `http://localhost:5678`. Change this only if you modified the plugin's port.

## Available Tools

Once installed, Claude will have access to ~25 Krita tools including:

### Document Management
- `krita_new_canvas` - Create new canvases
- `krita_open_file` - Open existing files
- `krita_save` - Save artwork
- `krita_get_canvas` - Export for inspection

### Drawing Tools
- `krita_stroke` - Paint strokes
- `krita_bulk_strokes` - Batch multiple strokes (performance)
- `krita_fill` - Fill areas
- `krita_draw_shape` - Draw shapes (rectangle, ellipse, line)

### Animation Tools
- `krita_create_keyframe` - Create animation keyframes
- `krita_set_current_frame` - Move timeline playhead
- `krita_list_keyframes` - List all keyframes
- `krita_enable_onion` - Toggle onion skinning

### Utility Tools
- `krita_health` - Check Krita connection
- `krita_set_color` - Set paint color
- `krita_set_brush` - Configure brush
- `krita_undo` / `krita_redo` - Undo/redo
- `krita_get_color_at` - Eyedropper tool

## Usage in Claude

Once installed, simply ask Claude to create art in Krita:

```
Create a 1920x1080 canvas and paint a sunset scene.
```

```
Create a 10-frame animation of a bouncing ball.
```

Claude will automatically use the Krita tools to execute your requests.

## Troubleshooting

### "Cannot connect to Krita" Error

1. Verify Krita is running
2. Check the plugin is enabled in Krita's Python Plugin Manager
3. Test the URL manually: http://localhost:5678/health
4. Check Windows Firewall isn't blocking port 5678
5. Verify the plugin is correctly installed in Krita's `pykrita/` folder

### Claude Doesn't See Krita Tools

1. Check Claude Desktop logs in `%APPDATA%\Claude\logs\`
2. Verify the extension is installed and enabled
3. Try restarting Claude Desktop
4. Check the extension configuration

### Timeouts on Large Operations

The extension has extended timeouts (120s) for export operations. If you still see timeouts:
- Reduce canvas size
- Use fewer strokes in bulk operations
- Close other heavy applications

## Security & Privacy

This extension:
- ✅ Operates entirely locally (no internet connections)
- ✅ Only communicates with Krita on localhost
- ✅ Does not access files outside Krita's control
- ✅ Does not require elevated privileges
- ✅ Does not send data to external servers

## Source Code

This is an open-source extension. View the source code and report issues:
- Repository: https://github.com/your-org/krita-mcp-claude
- License: MIT

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the main repository README
3. Open an issue on GitHub
