# Quick Installation Guide: Krita MCP Claude Extension

## Bundle Location

✅ **Ready to install**: `dist/krita-mcp-claude-uv.mcpb` (26.4 KB)

**NEW**: UV Runtime version - no system Python required!

---

## Prerequisites

1. ✅ **Claude Desktop** installed (version >=0.10.0)
2. ⚠️ **Krita** installed with MCP Bridge plugin (see below)
3. ~~**Python 3.8+**~~ **NOT REQUIRED** - Claude Desktop manages Python automatically via UV runtime!

---

## Step 1: Install Bundle in Claude Desktop

### Method A: Direct Installation (Recommended)

1. Open **Claude Desktop**
2. Go to **Settings → Extensions → Advanced settings**
3. Click **"Install Extension"** or **"Add Extension"**
4. Select: `C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude\dist\krita-mcp-claude-uv.mcpb`
5. **Verify Install button is ENABLED** (should show no Python warning)
6. Configure **Krita Plugin URL**: `http://localhost:5678` (default)
7. Click **Install**
8. **Wait 30-60 seconds** for first-time setup (Claude Desktop downloads dependencies)
9. **Restart Claude Desktop**

### Method B: Manual Configuration (If Direct Install Unavailable)

⚠️ **Note**: With UV runtime, manual configuration requires UV to be installed. Prefer Method A.

1. Extract the bundle:
   ```powershell
   Expand-Archive dist\krita-mcp-claude-uv.mcpb -DestinationPath C:\krita-mcp-extracted
   ```

2. Install UV if not already installed:
   ```powershell
   # Windows: Use pip or download from https://docs.astral.sh/uv/
   pip install uv
   ```

3. Edit Claude Desktop config:
   - Path: `%APPDATA%\Claude\claude_desktop_config.json`
   - Add this entry:
   ```json
   {
     "mcpServers": {
       "krita": {
         "command": "uv",
         "args": ["run", "--directory", "C:\\krita-mcp-extracted", "server.py"],
         "env": {
           "KRITA_URL": "http://localhost:5678"
         }
       }
     }
   }
   ```

4. **Restart Claude Desktop**

---

## Step 2: Install Krita MCP Bridge Plugin

**⚠️ CRITICAL**: The plugin is NOT included in the bundle and must be installed separately.

### Installation Steps

1. **Locate your Krita resources directory**:
   - Open Krita
   - Go to **Settings → Manage Resources → Open Resource Folder**
   - Navigate to the `pykrita/` subfolder
   - Note this path (e.g., `C:\Users\pavan\AppData\Roaming\krita\pykrita\`)

2. **Copy plugin files**:
   ```powershell
   # Copy the plugin folder
   Copy-Item -Recurse "C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude\krita-plugin\kritamcp" -Destination "C:\Users\pavan\AppData\Roaming\krita\pykrita\kritamcp"
   
   # Copy the desktop file
   Copy-Item "C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude\krita-plugin\kritamcp.desktop" -Destination "C:\Users\pavan\AppData\Roaming\krita\pykrita\kritamcp.desktop"
   ```

3. **Enable the plugin in Krita**:
   - In Krita: **Settings → Configure Krita → Python Plugin Manager**
   - Check the box next to **"Krita MCP Bridge"**
   - Click **OK**

4. **Restart Krita completely**

---

## Step 3: Verify Installation

### Test 1: Check Krita Plugin

1. Make sure Krita is running
2. Open PowerShell and run:
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:5678/health" | ConvertFrom-Json
   ```
3. Expected output:
   ```json
   {
     "plugin": "krita-mcp",
     "status": "ok",
     "version": "1.0"
   }
   ```

### Test 2: Check Claude Desktop Connection

1. Open Claude Desktop
2. Start a new conversation
3. Ask: **"What Krita tools do you currently have available?"**
4. Claude should list ~27 tools including:
   - `krita_health`
   - `krita_new_canvas`
   - `krita_stroke`
   - `krita_bulk_strokes`
   - `krita_create_keyframe`
   - etc.

### Test 3: Test Basic Operation

1. In Claude Desktop, ask:
   ```
   Check if Krita is connected.
   ```

2. Then:
   ```
   Create a 1920x1080 canvas named "Test Canvas" with a dark blue background.
   ```

3. Then:
   ```
   Draw a red circle in the center of the canvas.
   ```

4. Check Krita - you should see the canvas and circle appear!

---

## Troubleshooting

### "Cannot connect to Krita" Error

**Checklist**:
1. ✅ Is Krita running?
2. ✅ Is the plugin enabled in Krita's Python Plugin Manager?
3. ✅ Did you restart Krita after enabling the plugin?
4. ✅ Test the health endpoint manually: `http://localhost:5678/health`
5. ✅ Check Windows Firewall isn't blocking port 5678

**Fix**:
```powershell
# Test plugin directly
Invoke-WebRequest -Uri "http://localhost:5678/health"
```

### Claude Doesn't See Krita Tools

**Checklist**:
1. ✅ Did you restart Claude Desktop after installation?
2. ✅ Check Claude Desktop logs: `%APPDATA%\Claude\logs\`
3. ✅ Verify extension shows as "Enabled" in Claude settings

**Fix**:
- Completely quit Claude Desktop (check system tray)
- Restart Claude Desktop
- Try a new conversation

### "Python Requirement Not Satisfied" Warning

**This should NOT happen with the UV runtime bundle.**

If you see this warning:
1. Verify you're using `krita-mcp-claude-uv.mcpb` (not the old bundle)
2. Check the bundle was built correctly:
   ```powershell
   Expand-Archive dist\krita-mcp-claude-uv.mcpb -DestinationPath temp-check -Force
   Get-Content temp-check\manifest.json | ConvertFrom-Json | Select-Object manifest_version, @{N='server_type';E={$_.server.type}}
   Remove-Item temp-check -Recurse -Force
   ```
   Should show: `manifest_version: 0.4`, `server_type: uv`

3. Update Claude Desktop to the latest version (UV runtime requires recent Claude Desktop)

---

## What You Get

Once installed, Claude can:

### 🎨 Create Art
- Create canvases of any size
- Paint strokes with colors and brushes
- Draw shapes (circles, rectangles, lines)
- Fill areas with color

### 🎬 Create Animations
- Create keyframes on timeline
- Set playhead position
- Enable onion skinning
- Batch-draw multiple frames efficiently

### 🔧 Advanced Features
- Export canvases for inspection
- Save artwork to specific files
- Undo/redo operations
- Eyedropper color sampling
- List available brushes

### ⚡ Performance
- `krita_bulk_strokes` for batch operations (critical for animation)
- Extended timeouts for large operations
- Request ID tracking for debugging

### 🛡️ Reliability (P0 Fixes)
- State verification after operations
- Retry logic for unreliable operations
- File verification for saves/exports
- No silent failures

---

## Support

**Bundle Documentation**: See `BUNDLE_README.md` (included in bundle)

**Full Documentation**: See `README.md` in the project root

**Troubleshooting**: See `MCPB_PACKAGING_REPORT.md` for technical details

**Issues**: Report at project repository

---

## Next: Integration Testing

After installation, please run integration tests to validate P0 reliability:

1. Test document creation and verification
2. Test layer selection and verification
3. Test frame selection and verification
4. Test keyframe creation with retry logic
5. Test repeated operations for state synchronization
6. Check request IDs appear in logs
7. Verify no silent failures

See `INTEGRATION_TEST_INSTRUCTIONS.md` for detailed test protocol.

**Do not claim "production ready" until integration testing complete.**
