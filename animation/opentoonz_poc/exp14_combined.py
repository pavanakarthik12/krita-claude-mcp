"""
Combined test: NO_FRAME cell-id fix (this session's finding) + explicit
fx-graph terminal/xsheet/output wiring (last session's finding), applied
together to our REAL two-column mesh+Plastic scene, unmodified otherwise
(skeleton/keyframes untouched). Isolates whether the two known, source-backed
defects are jointly sufficient to produce visible pixels.
"""
import build_scene as bs
import shutil

mesh_level_id = 1
content_level_id = 2
mesh_col_id = 3
content_col_id = 4
content_fx_id = 5
xsheet_fx_id = 6
output_fx_id = 7

levels_xml = (
    bs.level_full_xml(mesh_level_id, "character_mesh", "character.mesh")
    + bs.level_full_xml(content_level_id, "character_art", "character_art.png")
)

mesh_col_xml = bs.mesh_column_xml(mesh_col_id, bs.level_ref_xml(mesh_level_id), frame_num="-2", span=3)

# content column WITH an explicit <fx> (full first-creation) - matches last
# session's exp4 finding that TXshLevelColumn's own <fx> tag is where the
# real, column-bound TLevelColumnFx object is created (loadData calls
# setColumn(this) only there).
content_cell = f'<cell>1 3 {bs.level_ref_xml(content_level_id)} -2 0</cell>'
content_col_fx_full = (
    f"<Toonz_columnFx id='{content_fx_id}'>"
    "<params></params><ports></ports>"
    f"<numberId>{content_fx_id}</numberId>"
    f'<fxId>"lvlColFx{content_fx_id}"</fxId><opened>1</opened>'
    "</Toonz_columnFx>"
)
content_col_xml = (
    f"<levelColumn id='{content_col_id}'>"
    "<status>0</status>"
    f"<cells>{content_cell}</cells>"
    f"<fx>{content_col_fx_full}</fx>"
    "</levelColumn>"
)

pegbars_xml = (
    bs.pegbar_xml("Col1", parent_id="Table", plastic_sd=bs.plastic_sd_xml(
        [
            {"name": "Root", "number": 1, "pos": (0.0, 0.0), "parent": None},
            {"name": "Child", "number": 2, "pos": (0.0, 5.0), "parent": 0},
        ],
        {
            "Root": {"hook": 1, "angle_keyframes": [], "distance_keyframes": []},
            "Child": {
                "hook": 2,
                "angle_keyframes": [(1, 0.0), (12, 45.0), (24, -30.0)],
                "distance_keyframes": [(1, 0.0), (12, 0.75), (24, 0.0)],
            },
        },
    ))
    + bs.pegbar_xml("Col2", parent_id="Col1", handle="", parent_handle="")
)

fxnodes_xml = (
    "<fxnodes>"
    f"<terminal><fxnode><Toonz_columnFx id='{content_fx_id}'/></fxnode></terminal>"
    f"<xsheet><Toonz_xsheetFx id='{xsheet_fx_id}'><params></params><ports></ports>"
    f"<numberId>{xsheet_fx_id}</numberId><fxId>\"xsh{xsheet_fx_id}\"</fxId><opened>1</opened></Toonz_xsheetFx></xsheet>"
    f"<output><Toonz_outputFx id='{output_fx_id}'><params></params>"
    f"<ports><source><Toonz_xsheetFx id='{xsheet_fx_id}'/></source></ports>"
    f"<numberId>{output_fx_id}</numberId><fxId>\"out{output_fx_id}\"</fxId><opened>1</opened></Toonz_outputFx></output>"
    "</fxnodes>"
)

xsheet_xml = (
    f"<columns>{mesh_col_xml}{content_col_xml}</columns>"
    f"<pegbars>{pegbars_xml}</pegbars>"
    f"{fxnodes_xml}"
)

tnz = (
    '<tnz version="82.0" framecount="3"><generator>exp14</generator>'
    f"<levelSet><levels>{levels_xml}</levels></levelSet>"
    f"<xsheet>{xsheet_xml}</xsheet></tnz>"
)

with open("output/exp14_combined.tnz", "w") as f:
    f.write(tnz)
print(tnz)
shutil.copy("output/exp14_combined.tnz", r"C:\OpenToonz stuff\sandbox\scenes\exp14_combined.tnz")
