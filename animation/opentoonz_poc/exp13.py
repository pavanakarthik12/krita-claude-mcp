import build_scene as bs
import shutil

levels_xml = (
    "<level id='1'>"
    '"simplename"'
    '<info dpix="72" dpiy="72"/>'
    '<path>"simplename.png"</path>'
    "</level>"
)
cell = f"<cell>1 1 {bs.level_ref_xml(1)} -1 0</cell>"
columns_xml = f"<levelColumn id='2'><status>0</status><cells>{cell}</cells></levelColumn>"
pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")
xsheet_xml = f"<columns>{columns_xml}</columns><pegbars>{pegbars_xml}</pegbars>"
tnz = (
    '<tnz version="82.0" framecount="1"><generator>exp13</generator>'
    f"<levelSet><levels>{levels_xml}</levels></levelSet>"
    f"<xsheet>{xsheet_xml}</xsheet></tnz>"
)
with open("output/exp13_simplename.tnz", "w") as f:
    f.write(tnz)
print(tnz)
shutil.copy("output/exp13_simplename.tnz", r"C:\OpenToonz stuff\sandbox\scenes\exp13_simplename.tnz")
