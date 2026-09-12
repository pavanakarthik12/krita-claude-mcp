# Claude Desktop Configuration for Krita MCP

This guide explains how to connect Claude Desktop to the Krita MCP server on Windows.

## Prerequisites

1. **Krita** installed and running
2. **Krita MCP plugin** installed (see Plugin Installation below)
3. **Claude Desktop** installed
4. **Python 3.8+** with required dependencies

## Step 1: Install Python Dependencies

```powershell
cd "C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Step 2: Install Krita Plugin

1. Copy the plugin folder:
   ```
   krita-plugin\kritamcp\
   ```

2. To your Krita resources directory. Find it in Krita:
   - Open Krita
   - Go to **Settings → Manage Resources → Open Resource Folder**
   - Navigate to `pykrita\` folder
   - Copy the `kritamcp` folder here

3. Restart Krita

4. Enable the plugin:
   - **Settings → Configure Krita → Python Plugin Manager**
   - Check **"Krita MCP Bridge"**
   - Click **OK**
   - Restart Krita again

## Step 3: Verify Krita Plugin is Running

Test the HTTP server:

```powershell
# Should return {"plugin": "krita-mcp", ...}
Invoke-WebRequest -Uri "http://localhost:5678/health" | ConvertFrom-Json
```

If this fails, check:
- Krita is running
- Plugin is enabled in Python Plugin Manager
- No firewall blocking port 5678

## Step 4: Configure Claude Desktop

1. Locate your Claude Desktop config file:
   ```
   %APPDATA%\Claude\claude_desktop_config.json
   ```

2. Add the Krita MCP server configuration:

```json
{
  "mcpServers": {
    "krita": {
      "command": "C:\\Users\\pavan\\OneDrive\\Desktop\\krita-mcp-claude\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\pavan\\OneDrive\\Desktop\\krita-mcp-claude\\server.py"
      ],
      "env": {
        "KRITA_URL": "http://localhost:5678"
      }
    }
  }
}
```

**IMPORTANT:** 
- Use **absolute paths** with double backslashes `\\`
- Use the Python executable from your virtual environment
- Adjust paths to match your actual installation location

## Step 5: Restart Claude Desktop

1. Completely quit Claude Desktop (check system tray)
2. Start Claude Desktop again
3. It will automatically launch the MCP server

## Step 6: Test in Claude

Start a new conversation and ask:

```
What Krita tools do you currently have available?
```

Claude should list ~30 Krita MCP tools including:
- krita_health
- krita_new_canvas
- krita_stroke
- krita_bulk_strokes
- krita_create_keyframe
- etc.

Then test basic operations:

```
Check if Krita is connected.
```

```
Create a 1920x1080 canvas named "Test Canvas".
```

```
Draw a red circle in the center of the canvas.
```

## Troubleshooting

### Claude doesn't see Krita tools

1. Check Claude Desktop logs:
   ```
   %APPDATA%\Claude\logs\
   ```

2. Look for MCP server errors

3. Verify paths in config are correct

### "Cannot connect to Krita" error

1. Ensure Krita is running
2. Check plugin is enabled
3. Test health endpoint manually (Step 3)
4. Check Windows Firewall

### Server won't start

1. Test manually:
   ```powershell
   cd "C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude"
   .venv\Scripts\Activate.ps1
   python server.py
   ```

2. Check for error messages in console
3. Verify dependencies installed: `pip list`

### Timeout errors

The server has extended timeouts for bulk operations (120s+). If you still see timeouts:

1. Reduce stroke count in bulk operations
2. Check Krita performance (CPU/memory)
3. Close other heavy applications

## Environment Variables

You can customize the Krita connection:

- `KRITA_URL` - Krita plugin HTTP server URL (default: `http://localhost:5678`)

## Security Note

The MCP server connects to Krita via localhost HTTP. It does NOT:
- Access the internet
- Execute arbitrary shell commands
- Access files outside Krita operations
- Require elevated privileges

All operations are scoped to Krita's API and the configured output directory (`~/krita-mcp-output`).

## Next Steps

Once connected, you can:

1. **Create static artwork** - Claude can draw, paint, use brushes
2. **Create animations** - Claude can create keyframes, manage timeline
3. **Inspect results** - Claude can export and analyze what it's drawn
4. **Iterate and refine** - Claude can make corrections based on feedback

See the main README.md for full tool documentation and animation workflow.
