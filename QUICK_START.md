# Quick Start: Install Krita MCP in Claude Desktop

**NEW**: UV Runtime - No Python installation required! 🎉

---

## 🎯 What You're Installing

**Bundle**: `dist/krita-mcp-claude-uv.mcpb` (26 KB)

**What it does**: Lets Claude control Krita - create art, paint, animate

**What you need**:
- Claude Desktop (>=0.10.0)
- Krita (with plugin installed separately)

**What you DON'T need**:
- ~~Python installation~~ ❌ (Claude Desktop handles it!)

---

## 🚀 Installation (3 Steps)

### Step 1: Install Extension in Claude Desktop

1. Open Claude Desktop
2. Settings → Extensions → Advanced settings → **Install Extension**
3. Select: `C:\Users\pavan\OneDrive\Desktop\krita-mcp-claude\dist\krita-mcp-claude-uv.mcpb`
4. ✅ Verify: Install button should be **ENABLED** (no Python warning)
5. Click **Install**
6. Wait 30-60 seconds (first-time: downloads dependencies)
7. Restart Claude Desktop

---

### Step 2: Install Krita Plugin

⚠️ **Separate step** - the plugin is NOT in the bundle.

**Copy plugin files**:
```powershell
# Copy plugin folder
Copy-Item -Recurse "krita-plugin\kritamcp" -Destination "$env:APPDATA\krita\pykrita\kritamcp"

# Copy desktop file
Copy-Item "krita-plugin\kritamcp.desktop" -Destination "$env:APPDATA\krita\pykrita\kritamcp.desktop"
```

**Enable in Krita**:
1. Open Krita
2. Settings → Configure Krita → Python Plugin Manager
3. Check ✅ "Krita MCP Bridge"
4. Click OK
5. **Restart Krita**

---

### Step 3: Verify

**Test plugin** (PowerShell):
```powershell
Invoke-WebRequest http://localhost:5678/health | ConvertFrom-Json
```

Expected: `{"plugin": "krita-mcp", "status": "ok"}`

**Test Claude**:
- Ask: "What Krita tools do you have?"
- Should list ~27 tools

**Test drawing**:
- Ask: "Create a 1920x1080 canvas and draw a red circle"
- Canvas should appear in Krita with red circle

---

## ❓ Troubleshooting

### Install Button Disabled

**Problem**: Python requirement warning, button disabled

**Diagnosis**:
```powershell
# Check bundle type
Expand-Archive dist\krita-mcp-claude-uv.mcpb -DestinationPath temp -Force
Get-Content temp\manifest.json | ConvertFrom-Json | Select-Object manifest_version, @{N='type';E={$_.server.type}}
Remove-Item temp -Recurse -Force
```

**Should show**:
- `manifest_version`: 0.4
- `type`: uv

**If wrong**: Bundle wasn't rebuilt. Run:
```powershell
mcpb pack . dist\krita-mcp-claude-uv.mcpb
```

---

### Claude Doesn't See Tools

**Checklist**:
- [ ] Extension installed?
- [ ] Claude Desktop restarted?
- [ ] New conversation started? (old ones don't update)
- [ ] Check logs: `%APPDATA%\Claude\logs\`

---

### "Cannot Connect to Krita" Error

**This is normal** if:
- Krita isn't running
- Plugin not installed
- Plugin not enabled

**Fix**:
1. Install plugin (Step 2 above)
2. Start Krita
3. Verify: `http://localhost:5678/health`

---

## 📚 Full Documentation

- **Installation Details**: `INSTALL_BUNDLE.md`
- **Verification Checklist**: `FINAL_VERIFICATION_CHECKLIST.md`
- **UV Runtime Fix**: `UV_RUNTIME_FIX_REPORT.md`
- **Original Docs**: `README.md`

---

## 🎉 Success Looks Like

**Claude Desktop**:
```
You: What Krita tools do you have?
Claude: I have 27 Krita tools available including:
- krita_new_canvas - Create canvases
- krita_stroke - Paint strokes
- krita_bulk_strokes - Batch drawing
- krita_create_keyframe - Animation
...
```

**Krita**:
```
You: Create a 1920x1080 canvas and paint a sunset
Claude: [Creates canvas, paints sunset]
```

Canvas appears in Krita with painted sunset! 🎨

---

**Questions?** Check `FINAL_VERIFICATION_CHECKLIST.md` for detailed testing guide.

**Ready? Start with Step 1! 🚀**
