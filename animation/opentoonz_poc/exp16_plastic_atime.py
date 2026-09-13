"""
EXPERIMENT 2: existing Plastic (mesh+content) scene, both files' atime
measured across a real render, controlling for the row-0 off-by-one
(tcomposer.cpp:436) by regenerating build_scene.py's output with cells that
start at row 0 for this test only (via direct string patch, not by editing
build_scene.py itself).
"""
import os
import time
import subprocess
from PIL import Image

SANDBOX = r"C:\OpenToonz stuff\sandbox"
SCENES_DIR = os.path.join(SANDBOX, "scenes")
TCOMPOSER = r"C:\Program Files\OpenToonz\tcomposer.exe"


def touch_old(path):
    old = time.time() - 3600
    os.utime(path, (old, old))


with open(os.path.join(SCENES_DIR, "poc_scene.tnz"), "r", encoding="ascii") as f:
    scene = f.read()

# Patch row 1 -> row 0 for both cells (row-0 coverage), leaving everything
# else (skeleton, keyframes, mesh geometry) untouched - a mechanical,
# source-justified patch (tcomposer.cpp:436), not a speculative one.
patched = scene.replace("<cell>1 24", "<cell>0 24")
assert patched != scene, "expected exactly the row=1 cells to be patched"

patched_path = os.path.join(SCENES_DIR, "poc_scene_row0.tnz")
with open(patched_path, "w", encoding="ascii") as f:
    f.write(patched)

art = os.path.join(SCENES_DIR, "character_art.png")
mesh = os.path.join(SCENES_DIR, "character.mesh")
touch_old(art)
touch_old(mesh)
art_before, mesh_before = os.path.getatime(art), os.path.getatime(mesh)

for fn in os.listdir(SANDBOX):
    if fn.startswith("poc_row0_out"):
        os.remove(os.path.join(SANDBOX, fn))

r = subprocess.run(
    [TCOMPOSER, "poc_scene_row0.tnz", "-o", "poc_row0_out.png", "-range", "1", "3"],
    cwd=SCENES_DIR, capture_output=True, text=True, timeout=30,
)

art_after, mesh_after = os.path.getatime(art), os.path.getatime(mesh)

print("=== EXPERIMENT 2: existing Plastic scene, row-0-covered, atime for BOTH files ===")
print("stdout:", r.stdout.strip().replace("\n", " | "))
print("stderr:", r.stderr.strip())
print(f"character_art.png: before={art_before:.2f} after={art_after:.2f} ACCESSED={art_after > art_before}")
print(f"character.mesh:    before={mesh_before:.2f} after={mesh_after:.2f} ACCESSED={mesh_after > mesh_before}")

for i in range(1, 4):
    p = os.path.join(SANDBOX, f"poc_row0_out.{i:04d}.png")
    if os.path.exists(p):
        img = Image.open(p).convert("RGBA")
        print(f"  frame {i}: extrema={img.getextrema()} bbox={img.getbbox()}")
    else:
        print(f"  frame {i}: MISSING")
