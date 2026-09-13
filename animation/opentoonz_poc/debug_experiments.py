"""
Controlled experiments for the "all frames render transparent" bug.
Each experiment is a minimal variant of the scene, rendered via the real
tcomposer binary inside the existing 'sandbox' OpenToonz project (required
for headless project resolution - see the POC report), with pixel stats
checked after each run. This isolates which piece of the pipeline is at
fault rather than guessing.
"""
import os
import shutil
import subprocess
from PIL import Image

import build_scene as bs

SANDBOX = r"C:\OpenToonz stuff\sandbox"
SCENES_DIR = os.path.join(SANDBOX, "scenes")
TCOMPOSER = r"C:\Program Files\OpenToonz\tcomposer.exe"


def render(scene_name, out_prefix, frame_range=(1, 1), timeout=30):
    for f in os.listdir(SANDBOX):
        if f.startswith(out_prefix):
            os.remove(os.path.join(SANDBOX, f))
    cmd = [
        TCOMPOSER, scene_name, "-o", out_prefix + ".png",
        "-range", str(frame_range[0]), str(frame_range[1]),
    ]
    result = subprocess.run(cmd, cwd=SCENES_DIR, capture_output=True,
                             text=True, timeout=timeout)
    return result


def pixel_stats(png_path):
    img = Image.open(png_path).convert("RGBA")
    extrema = img.getextrema()
    bbox = img.getbbox()
    return extrema, bbox


def check_frame(out_prefix, frame_num=1):
    path = os.path.join(SANDBOX, f"{out_prefix}.{frame_num:04d}.png")
    if not os.path.exists(path):
        return None, None, False
    extrema, bbox = pixel_stats(path)
    nonblank = bbox is not None
    return extrema, bbox, nonblank


def write_and_copy(xml_text, name):
    local_path = os.path.join("output", name)
    with open(local_path, "w", encoding="ascii") as f:
        f.write(xml_text)
    shutil.copy(local_path, os.path.join(SCENES_DIR, name))
    return name


# ---------------------------------------------------------------------------
# Experiment 1: bare single raster column, NO mesh, NO plasticSD, NO parenting.
# ---------------------------------------------------------------------------
def experiment_1_bare_raster_column():
    persist_id_level = 1
    persist_id_col = 2
    levels_xml = bs.level_full_xml(persist_id_level, "character_art", "character_art.png")
    columns_xml = bs.level_column_xml(persist_id_col, bs.level_ref_xml(persist_id_level), span=1)
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
    tnz = (
        '<tnz version="82.0" framecount="1">'
        "<generator>exp1</generator>"
        f"<levelSet><levels>{levels_xml}</levels></levelSet>"
        f"<xsheet>{xsheet_xml}</xsheet>"
        "</tnz>"
    )
    name = write_and_copy(tnz, "exp1_bare_raster.tnz")
    r = render(name, "exp1_out")
    extrema, bbox, nonblank = check_frame("exp1_out")
    print("EXPERIMENT 1 (bare raster column, no mesh/plastic):")
    print("  stdout:", r.stdout.strip().replace("\n", " | "))
    print("  stderr:", r.stderr.strip())
    print("  extrema:", extrema, "bbox:", bbox, "NONBLANK:", nonblank)
    return nonblank


def experiment_2_solid_opaque_explicit_dpi():
    persist_id_level = 1
    persist_id_col = 2
    # explicit dpix/dpiy (avoids relying on DP_ImageDpi / embedded PNG dpi
    # metadata, which PIL-written PNGs may lack), fully opaque solid color
    # (rules out alpha/premultiply as the cause of "all zero" pixels).
    levels_xml = (
        f"<level id='{persist_id_level}'>"
        '"solid_red"'
        '<info dpix="72" dpiy="72"/>'
        '<path>"solid_red.png"</path>'
        "</level>"
    )
    columns_xml = bs.level_column_xml(persist_id_col, bs.level_ref_xml(persist_id_level), span=1)
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
    tnz = (
        '<tnz version="82.0" framecount="1">'
        "<generator>exp2</generator>"
        f"<levelSet><levels>{levels_xml}</levels></levelSet>"
        f"<xsheet>{xsheet_xml}</xsheet>"
        "</tnz>"
    )
    name = write_and_copy(tnz, "exp2_solid_opaque.tnz")
    r = render(name, "exp2_out")
    extrema, bbox, nonblank = check_frame("exp2_out")
    print("EXPERIMENT 2 (solid opaque 200x200 red, explicit dpi=72):")
    print("  stdout:", r.stdout.strip().replace("\n", " | "))
    print("  stderr:", r.stderr.strip())
    print("  extrema:", extrema, "bbox:", bbox, "NONBLANK:", nonblank)
    return nonblank


def fxnode_column_fx_full(persist_id):
    return (
        f"<Toonz_columnFx id='{persist_id}'>"
        "<params></params>"
        "<ports></ports>"
        f"<numberId>{persist_id}</numberId>"
        f'<fxId>"lvlColFx{persist_id}"</fxId>'
        "<opened>1</opened>"
        "</Toonz_columnFx>"
    )


def fxnode_column_fx_ref(persist_id):
    return f"<Toonz_columnFx id='{persist_id}'/>"


def fxnode_xsheet_fx_full(persist_id):
    return (
        f"<Toonz_xsheetFx id='{persist_id}'>"
        "<params></params><ports></ports>"
        f"<numberId>{persist_id}</numberId>"
        f'<fxId>"xsheetFx{persist_id}"</fxId>'
        "<opened>1</opened>"
        "</Toonz_xsheetFx>"
    )


def fxnode_xsheet_fx_ref(persist_id):
    return f"<Toonz_xsheetFx id='{persist_id}'/>"


def fxnode_output_fx_full(persist_id, xsheet_fx_ref_xml):
    return (
        f"<Toonz_outputFx id='{persist_id}'>"
        "<params></params>"
        f"<ports><source>{xsheet_fx_ref_xml}</source></ports>"
        f"<numberId>{persist_id}</numberId>"
        f'<fxId>"outputFx{persist_id}"</fxId>'
        "<opened>1</opened>"
        "</Toonz_outputFx>"
    )


def experiment_4_full_fx_wiring():
    """
    Root-cause test: FxBuilder::buildFx() (scenefx.cpp) requires
    xsh->getFxDag()->getOutputFx(0) to have its single input port connected,
    and (since m_expandXSheet defaults true) TXsheetFx expansion reads
    getTerminalFxs() - which is EMPTY unless <fxnodes> explicitly restores
    it. TXshLevelColumn's own <fx> tag is where the REAL, column-bound
    TLevelColumnFx object gets its first full read (loadData calls
    setColumn(this) only there); <fxnodes><terminal> must then reference
    that SAME persist id (a plain factory-created object would have
    m_levelColumn == nullptr).
    """
    persist_id_level = 1
    persist_id_col = 2
    fx_id = 3
    xsheet_fx_id = 4
    output_fx_id = 5

    levels_xml = (
        f"<level id='{persist_id_level}'>"
        '"solid_red"'
        '<info dpix="72" dpiy="72"/>'
        '<path>"solid_red.png"</path>'
        "</level>"
    )
    cell = f"<cell>1 1 {bs.level_ref_xml(persist_id_level)} 1 0</cell>"
    columns_xml = (
        f"<levelColumn id='{persist_id_col}'>"
        "<status>0</status>"
        f"<cells>{cell}</cells>"
        f"<fx>{fxnode_column_fx_full(fx_id)}</fx>"
        "</levelColumn>"
    )
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    fxnodes_xml = (
        "<fxnodes>"
        f"<terminal><fxnode>{fxnode_column_fx_ref(fx_id)}</fxnode></terminal>"
        f"<xsheet>{fxnode_xsheet_fx_full(xsheet_fx_id)}</xsheet>"
        f"<output>{fxnode_output_fx_full(output_fx_id, fxnode_xsheet_fx_ref(xsheet_fx_id))}</output>"
        "</fxnodes>"
    )
    xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>{fxnodes_xml}"
    tnz = (
        '<tnz version="82.0" framecount="1">'
        "<generator>exp4</generator>"
        f"<levelSet><levels>{levels_xml}</levels></levelSet>"
        f"<xsheet>{xsheet_xml}</xsheet>"
        "</tnz>"
    )
    name = write_and_copy(tnz, "exp4_full_fx.tnz")
    r = render(name, "exp4_out")
    extrema, bbox, nonblank = check_frame("exp4_out")
    print("EXPERIMENT 4 (full fx wiring: column <fx> + <fxnodes> terminal/xsheet/output):")
    print("  stdout:", r.stdout.strip().replace("\n", " | "))
    print("  stderr:", r.stderr.strip())
    print("  extrema:", extrema, "bbox:", bbox, "NONBLANK:", nonblank)
    return nonblank


def experiment_3_row_zero_and_wide_range():
    persist_id_level = 1
    persist_id_col = 2
    levels_xml = (
        f"<level id='{persist_id_level}'>"
        '"solid_red"'
        '<info dpix="72" dpiy="72"/>'
        '<path>"solid_red.png"</path>'
        "</level>"
    )
    # row=0 instead of row=1, rowCount=5 to cover several candidate frame
    # indices regardless of 0/1-based row addressing.
    cell = f"<cell>0 5 {bs.level_ref_xml(persist_id_level)} 1 0</cell>"
    columns_xml = (
        f"<levelColumn id='{persist_id_col}'>"
        "<status>0</status>"
        f"<cells>{cell}</cells>"
        "</levelColumn>"
    )
    pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
    xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
    tnz = (
        '<tnz version="82.0" framecount="5">'
        "<generator>exp3</generator>"
        f"<levelSet><levels>{levels_xml}</levels></levelSet>"
        f"<xsheet>{xsheet_xml}</xsheet>"
        "</tnz>"
    )
    name = write_and_copy(tnz, "exp3_row_zero.tnz")
    r = render(name, "exp3_out", frame_range=(0, 5))
    print("EXPERIMENT 3 (row=0, rowCount=5, render range 0..5):")
    print("  stdout:", r.stdout.strip().replace("\n", " | "))
    print("  stderr:", r.stderr.strip())
    for i in range(0, 6):
        extrema, bbox, nonblank = check_frame("exp3_out", i)
        print(f"  frame {i}: extrema={extrema} bbox={bbox} nonblank={nonblank}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    experiment_4_full_fx_wiring()
