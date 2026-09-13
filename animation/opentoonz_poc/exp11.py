import build_scene as bs
import shutil

pegbars_xml = bs.pegbar_xml("Col1", parent_id="Table")

fxnodes_xml = (
    "<fxnodes>"
    "<terminal><fxnode>"
    "<checkBoardFx id='1'><params></params><ports></ports>"
    "<numberId>1</numberId><fxId>\"cb1\"</fxId><opened>1</opened>"
    "</checkBoardFx>"
    "</fxnode></terminal>"
    "<xsheet><Toonz_xsheetFx id='2'><params></params><ports></ports>"
    "<numberId>2</numberId><fxId>\"xsh2\"</fxId><opened>1</opened></Toonz_xsheetFx></xsheet>"
    "<output><Toonz_outputFx id='3'><params></params>"
    "<ports><source><Toonz_xsheetFx id='2'/></source></ports>"
    "<numberId>3</numberId><fxId>\"out3\"</fxId><opened>1</opened></Toonz_outputFx></output>"
    "</fxnodes>"
)

xsheet_xml = f"<columns></columns><pegbars>{pegbars_xml}</pegbars>{fxnodes_xml}"
tnz = (
    '<tnz version="82.0" framecount="1"><generator>exp11</generator>'
    f"<xsheet>{xsheet_xml}</xsheet></tnz>"
)
with open("output/exp11_checkboard.tnz", "w") as f:
    f.write(tnz)
print(tnz)
shutil.copy("output/exp11_checkboard.tnz", r"C:\OpenToonz stuff\sandbox\scenes\exp11_checkboard.tnz")
