import build_scene as bs
import shutil

abs_path = "C:/OpenToonz stuff/sandbox/scenes/plain_rgb_blue.png"
levels_xml = (
    "<level id='1'>"
    '"lvl_emptyframe_test"'
    '<info dpix="72" dpiy="72"/>'
    f'<path>"{abs_path}"</path>'
    "</level>"
)
# frame id string "-1" == TFrameId::EMPTY_FRAME per qstringToFrameId - the
# convention for a level that is a single un-numbered image file, not part
# of a "name.####.ext" numbered sequence.
cell = f"<cell>1 1 {bs.level_ref_xml(1)} -1 0</cell>"
columns_xml = f"<levelColumn id='2'><status>0</status><cells>{cell}</cells></levelColumn>"
pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
tnz = (
    '<tnz version="82.0" framecount="1"><generator>exp12</generator>'
    f"<levelSet><levels>{levels_xml}</levels></levelSet>"
    f"<xsheet>{xsheet_xml}</xsheet></tnz>"
)
with open("output/exp12_emptyframe.tnz", "w") as f:
    f.write(tnz)
print(tnz)
shutil.copy("output/exp12_emptyframe.tnz", r"C:\OpenToonz stuff\sandbox\scenes\exp12_emptyframe.tnz")
