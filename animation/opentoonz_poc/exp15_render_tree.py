"""
Render-tree diagnostic session. Controls for the row-0/frame-0 off-by-one
found in tcomposer.cpp:436 ("riporto gli indici a base zero": r0 = r0 - 1),
which means "-range 1 N" queries internal frame indices 0..N-1, i.e. row 0
first - a row none of our previous scenes ever populated (cells always
started at row 1). Every cell below starts at row 0 to eliminate that
confound before asking the render-tree-membership question.

Each experiment reports os.path.getatime() (mtime is untouched by reads;
atime is the direct, OS-level "was this file opened for reading" signal)
before and after a real tcomposer render, plus pixel extrema.
"""
import os
import shutil
import subprocess
import time
from PIL import Image

import build_scene as bs

SANDBOX = r"C:\OpenToonz stuff\sandbox"
SCENES_DIR = os.path.join(SANDBOX, "scenes")
TCOMPOSER = r"C:\Program Files\OpenToonz\tcomposer.exe"


def atime(path):
    return os.path.getatime(path)


def touch_atime_baseline(path):
    # Force a known-old atime so a real render's access is unambiguous even
    # under any OS-level atime-update throttling.
    old = time.time() - 3600
    os.utime(path, (old, old))


def render(scene_name, out_prefix, frame_range=(1, 1), timeout=30):
    for f in os.listdir(SANDBOX):
        if f.startswith(out_prefix):
            os.remove(os.path.join(SANDBOX, f))
    cmd = [TCOMPOSER, scene_name, "-o", out_prefix + ".png",
           "-range", str(frame_range[0]), str(frame_range[1])]
    return subprocess.run(cmd, cwd=SCENES_DIR, capture_output=True, text=True, timeout=timeout)


def pixel_report(out_prefix, n):
    results = []
    for i in range(1, n + 1):
        p = os.path.join(SANDBOX, f"{out_prefix}.{i:04d}.png")
        if not os.path.exists(p):
            results.append((i, None, None))
            continue
        img = Image.open(p).convert("RGBA")
        results.append((i, img.getextrema(), img.getbbox()))
    return results


def write_and_copy(xml_text, name):
    local_path = os.path.join("output", name)
    with open(local_path, "w", encoding="ascii") as f:
        f.write(xml_text)
    shutil.copy(local_path, os.path.join(SCENES_DIR, name))
    return name


# ---------------------------------------------------------------------------
# EXPERIMENT 1: content-only scene. One levelColumn, one PNG level, row 0
# populated, no mesh column, no Plastic, no <fxnodes> (baseline: does a
# maximally plain column with a correctly-covered row 0 get its file opened
# at all?).
# ---------------------------------------------------------------------------
def experiment_1():
    level_xml = bs.level_full_xml(1, "character_art", "character_art.png")
    cell = f"<cell>0 3 {bs.level_ref_xml(1)} -2 0</cell>"  # rows 0,1,2
    col_xml = f"<levelColumn id='2'><status>0</status><cells>{cell}</cells></levelColumn>"
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    xsheet_xml = f"<columns>{col_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
    tnz = ('<tnz version="82.0" framecount="3"><generator>exp15_1</generator>'
           f"<levelSet><levels>{level_xml}</levels></levelSet>"
           f"<xsheet>{xsheet_xml}</xsheet></tnz>")
    name = write_and_copy(tnz, "exp15_1_content_only.tnz")

    art_path = os.path.join(SCENES_DIR, "character_art.png")
    touch_atime_baseline(art_path)
    before = atime(art_path)

    r = render(name, "exp15_1_out", frame_range=(1, 3))
    after = atime(art_path)

    print("=== EXPERIMENT 1: content-only, row-0-populated, no fx wiring ===")
    print("stdout:", r.stdout.strip().replace("\n", " | "))
    print("stderr:", r.stderr.strip())
    print(f"character_art.png atime before={before:.2f} after={after:.2f} ACCESSED={after > before}")
    for i, extrema, bbox in pixel_report("exp15_1_out", 3):
        print(f"  frame {i}: extrema={extrema} bbox={bbox}")
    print()


# ---------------------------------------------------------------------------
# EXPERIMENT 1b: same as experiment 1, but WITH the <fx>/<fxnodes> terminal-
# xsheet-output wiring (last session's finding) added. Isolates whether that
# wiring alone is sufficient to bring the column's fx into TXsheetFx's
# expansion (scenefx.cpp:778, "Expand the render-tree from terminal fxs").
# ---------------------------------------------------------------------------
def experiment_1b():
    level_xml = bs.level_full_xml(1, "character_art", "character_art.png")
    cell = f"<cell>0 3 {bs.level_ref_xml(1)} -2 0</cell>"
    fx_full = (
        "<Toonz_columnFx id='3'><params></params><ports></ports>"
        "<numberId>3</numberId><fxId>\"lvlColFx3\"</fxId><opened>1</opened>"
        "</Toonz_columnFx>"
    )
    col_xml = (
        f"<levelColumn id='2'><status>0</status><cells>{cell}</cells>"
        f"<fx>{fx_full}</fx></levelColumn>"
    )
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    fxnodes_xml = (
        "<fxnodes>"
        "<terminal><fxnode><Toonz_columnFx id='3'/></fxnode></terminal>"
        "<xsheet><Toonz_xsheetFx id='4'><params></params><ports></ports>"
        "<numberId>4</numberId><fxId>\"xsh4\"</fxId><opened>1</opened></Toonz_xsheetFx></xsheet>"
        "<output><Toonz_outputFx id='5'><params></params>"
        "<ports><source><Toonz_xsheetFx id='4'/></source></ports>"
        "<numberId>5</numberId><fxId>\"out5\"</fxId><opened>1</opened></Toonz_outputFx></output>"
        "</fxnodes>"
    )
    xsheet_xml = f"<columns>{col_xml}</columns><pegbars>{pegbars_xml}</pegbars>{fxnodes_xml}"
    tnz = ('<tnz version="82.0" framecount="3"><generator>exp15_1b</generator>'
           f"<levelSet><levels>{level_xml}</levels></levelSet>"
           f"<xsheet>{xsheet_xml}</xsheet></tnz>")
    name = write_and_copy(tnz, "exp15_1b_content_fxwired.tnz")

    art_path = os.path.join(SCENES_DIR, "character_art.png")
    touch_atime_baseline(art_path)
    before = atime(art_path)

    r = render(name, "exp15_1b_out", frame_range=(1, 3))
    after = atime(art_path)

    print("=== EXPERIMENT 1b: content-only, row-0-populated, WITH fx wiring ===")
    print("stdout:", r.stdout.strip().replace("\n", " | "))
    print("stderr:", r.stderr.strip())
    print(f"character_art.png atime before={before:.2f} after={after:.2f} ACCESSED={after > before}")
    for i, extrema, bbox in pixel_report("exp15_1b_out", 3):
        print(f"  frame {i}: extrema={extrema} bbox={bbox}")
    print()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    experiment_1()
    experiment_1b()
