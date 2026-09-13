"""
Hand-authors a minimal OpenToonz .tnz scene file exercising the Plastic
skeleton/mesh/deformation pipeline, following the EXACT tag structure found
by reading the OpenToonz source at C:\\Users\\pavan\\OneDrive\\Desktop\\opentoonz:

  toonz/sources/toonzlib/toonzscene.cpp      -> ToonzScene::save/loadTnzFile
                                                 (top-level <tnz>, <levelSet>, <xsheet>)
  toonz/sources/toonzlib/levelset.cpp        -> TLevelSet::saveData (<levels>)
  toonz/sources/toonzlib/txshsimplelevel.cpp -> TXshSimpleLevel::saveData (<level>)
  toonz/sources/toonzlib/txsheet.cpp         -> TXsheet::saveData (<columns>, <pegbars>)
  toonz/sources/toonzlib/txshmeshcolumn.cpp  -> TXshMeshColumn::saveData (<meshColumn>)
  toonz/sources/toonzlib/txshlevelcolumn.cpp -> TXshLevelColumn::saveData (<levelColumn>)
  toonz/sources/toonzlib/tstageobjecttree.cpp-> TStageObjectTree::saveData (<pegbars>/<pegbar>)
  toonz/sources/toonzlib/tstageobject.cpp    -> TStageObject::saveData (<parent>,<center>,<plasticSD>...)
  toonz/sources/tnzext/plasticskeleton.cpp   -> PlasticSkeleton::saveData (<V>,<E>)
  toonz/sources/tnzext/plasticskeletondeformation.cpp
                                              -> PlasticSkeletonDeformation::saveData
                                                 (<VertexDeforms>,<SkelIdsParam>,<Skeletons>)
  toonz/sources/common/tparam/tdoubleparam.cpp     -> TDoubleParam::saveData (<default>,<keyframes>)
  toonz/sources/common/tparam/tdoublekeyframe.cpp  -> TDoubleKeyframe::saveData (<L> linear keyframe)

KEY ARCHITECTURAL FACT this scene depends on (found in
toonz/sources/toonzlib/scenefx.cpp, FxBuilder::addPlasticDeformerFx):
Plastic deformation is applied AUTOMATICALLY by the renderer, at render-graph
build time, whenever a column's stage-object PARENT is a column holding a
MESH_XSHLEVEL level whose stage-object carries a <plasticSD>. It is NOT a
user-visible fx node in <fxnodes> - so this scene deliberately has NO
<fxnodes> section at all (confirmed optional: TXsheet::loadData iterates
`while (is.openChild(tagName))`, so any top-level xsheet section - including
fxnodes - may be omitted).

Two columns are therefore required:
  Col1 = the MESH level column (the "Plastic mesh" + its skeleton)
  Col2 = the content column (a plain PNG "drawing"), parented to Col1
"""
import os


# ---------------------------------------------------------------------------
# TStream primitive helpers (reproducing TOStream's plain-text conventions)
# ---------------------------------------------------------------------------

def q(s):
    """Quote a string the way TOStream::operator<<(std::wstring) does."""
    return f'"{s}"'


def linear_keyframe(frame, value, has_prev):
    if has_prev:
        return f"<L><prev>{value}</prev>{frame} {value}</L>"
    return f"<L>{frame} {value}</L>"


def double_param(default, keyframes):
    """keyframes: list of (frame, value), already sorted by frame."""
    parts = [f"<default>{default}</default>"]
    if keyframes:
        kf_xml = []
        for i, (frame, value) in enumerate(keyframes):
            kf_xml.append(linear_keyframe(frame, value, has_prev=(i > 0)))
        parts.append("<keyframes>" + "".join(kf_xml) + "</keyframes>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# PlasticSkeleton (<V>, <E>) - matches plasticskeleton.cpp exactly
# ---------------------------------------------------------------------------

def plastic_skeleton_xml(vertices):
    """
    vertices: list of dicts {name, number, pos:(x,y), parent(index or None)}
    First vertex (index 0) must be the root (parent=None).
    """
    v_xml = [str(len(vertices))]
    edges = []
    for i, vx in enumerate(vertices):
        v_xml.append(
            "<Vertex>"
            f"<name>{q(vx['name'])}</name>"
            f"<number>{vx['number']}</number>"
            f"<pos>{vx['pos'][0]} {vx['pos'][1]}</pos>"
            f"<interpolate>1</interpolate>"
            "</Vertex>"
        )
        if vx["parent"] is not None:
            edges.append((vx["parent"], i))

    e_xml = [str(len(edges))]
    for v0, v1 in edges:
        e_xml.append(f"{v0} {v1}")

    return "<V>" + " ".join(v_xml) + "</V><E>" + " ".join(e_xml) + "</E>"


# ---------------------------------------------------------------------------
# PlasticSkeletonDeformation (<plasticSD>) - matches
# plasticskeletondeformation.cpp exactly
# ---------------------------------------------------------------------------

def plastic_sd_xml(vertices, vertex_deforms):
    """
    vertex_deforms: dict vertex_name -> {"hook": int,
                                          "angle_keyframes": [(f,v),...],
                                          "distance_keyframes": [(f,v),...]}
    """
    vd_xml = []
    for vx in vertices:
        name = vx["name"]
        vd = vertex_deforms[name]
        angle = double_param(0.0, vd.get("angle_keyframes", []))
        distance = double_param(0.0, vd.get("distance_keyframes", []))
        vd_body = f"<Angle>{angle}</Angle><Distance>{distance}</Distance>"
        vd_xml.append(
            f"<Name>{q(name)}</Name><Hook>{vd['hook']}</Hook><VD>{vd_body}</VD>"
        )

    skeleton_xml = plastic_skeleton_xml(vertices)

    return (
        "<plasticSD>"
        "<VertexDeforms>" + "".join(vd_xml) + "</VertexDeforms>"
        "<SkelIdsParam><default>1</default></SkelIdsParam>"
        "<Skeletons>"
        "<SkelId>1</SkelId>"
        f"<Skeleton>{skeleton_xml}</Skeleton>"
        "</Skeletons>"
        "</plasticSD>"
    )


# ---------------------------------------------------------------------------
# TStageObject (<pegbar>) - matches tstageobject.cpp TStageObject::saveData
# ---------------------------------------------------------------------------

def pegbar_xml(obj_id, parent_id="Table", handle="", parent_handle="",
               plastic_sd=None):
    parent_tag = (
        f'<parent id="{parent_id}" handle="{handle}" '
        f'parentHandle="{parent_handle}"></parent>'
    )
    body = [
        parent_tag,
        "<isOpened>0</isOpened>",
        "<center>0 0 0 0</center>",
        "<status>0</status>",
    ]
    if plastic_sd:
        body.append(plastic_sd)
    body.append("<nodePos>0 0</nodePos>")
    return f'<pegbar id="{obj_id}">' + "".join(body) + "</pegbar>"


# ---------------------------------------------------------------------------
# TXshSimpleLevel (<level>) - matches txshsimplelevel.cpp saveData
# ---------------------------------------------------------------------------

_persist_id_counter = [0]


def next_persist_id():
    _persist_id_counter[0] += 1
    return _persist_id_counter[0]


def level_full_xml(persist_id, name, relative_path):
    # NOTE: <info> MUST be self-closed - TXshSimpleLevel::loadData's "info"
    # branch (txshsimplelevel.cpp) never calls is.matchEndTag()/closeChild()
    # for it, unlike "path"/"scannedPath" which do. A paired <info></info>
    # leaves a stray, unconsumed close tag that desyncs the rest of the
    # parse (empirically confirmed: caused a bogus "unable to create a
    # persistent 'path'" TPersistFactory error further down the stream).
    return (
        f"<level id='{persist_id}'>"
        f"{q(name)}"
        '<info dpiType="image"/>'
        f"<path>{q(relative_path)}</path>"
        "</level>"
    )


def level_ref_xml(persist_id):
    return f"<level id='{persist_id}'/>"


# ---------------------------------------------------------------------------
# Columns (<meshColumn>, <levelColumn>) - matches txshmeshcolumn.cpp /
# txshlevelcolumn.cpp saveData
# ---------------------------------------------------------------------------

def mesh_column_xml(persist_id, level_ref, frame_num="-2", span=24):
    # rowCount=span repeats the single mesh frame across the whole
    # timeline range (increment=0) - the shape itself doesn't change per
    # level-frame, only its POSE (via the keyframed plasticSD curves).
    #
    # frame_num="-2" == TFrameId::NO_FRAME (tfilepath.h:39, "e.g. pippo.tif" -
    # a plain, single-dot filename with no frame-number token). Our level
    # file ("character.mesh") is exactly such a file. TLevelReader::loadInfo()
    # (tlevel_io.cpp:102) has no per-level-type override for MESH_XSHLEVEL,
    # so it uses the generic base-class directory scan, which calls
    # TFilePath::getFrame() (tfilepath.cpp:778) on every matching file.
    # getFrame() returns NO_FRAME whenever no numeric frame segment is found
    # (confirmed by tracing "character.mesh": no second dot, and its one
    # underscore-free base name yields no numeric split either way -> falls
    # straight through to `if (j == npos) return TFrameId(NO_FRAME);`).
    # A cell requesting frame "1" (TFrameId(1)) therefore looks up a
    # different map key than what the reader actually registered.
    cell = f"<cell>1 {span} {level_ref} {frame_num} 0</cell>"
    return (
        f"<meshColumn id='{persist_id}'>"
        "<status>0</status>"
        f"<cells>{cell}</cells>"
        "</meshColumn>"
    )


def level_column_xml(persist_id, level_ref, frame_num="-2", span=24):
    # <fx> is intentionally omitted: TXshLevelColumn::loadData treats it as
    # optional (the enclosing tag loop just skips tags it doesn't see), and
    # an empty <fx></fx> would make the inner `is >> p` (TPersist* read) see
    # only the immediate close tag and throw "expected begin tag". Omitting
    # it leaves m_fx at its default-constructed value, which is fine here.
    #
    # frame_num="-2" == TFrameId::NO_FRAME - see mesh_column_xml() above for
    # the full source trace. "character_art.png" is likewise a plain,
    # single-dot filename with no numeric frame token, so the reader's
    # directory scan (TLevelReader::loadInfo(), tlevel_io.cpp:102) registers
    # it under NO_FRAME, not under the numeric id "1" the cell previously
    # requested.
    cell = f"<cell>1 {span} {level_ref} {frame_num} 0</cell>"
    return (
        f"<levelColumn id='{persist_id}'>"
        "<status>0</status>"
        f"<cells>{cell}</cells>"
        "</levelColumn>"
    )


# ---------------------------------------------------------------------------
# Full scene assembly
# ---------------------------------------------------------------------------

def build_scene_xml(mesh_level_path, content_level_path, frame_count=24):
    mesh_level_id = next_persist_id()   # 1
    content_level_id = next_persist_id()  # 2
    mesh_col_id = next_persist_id()     # 3
    content_col_id = next_persist_id()  # 4

    levels_xml = (
        level_full_xml(mesh_level_id, "character_mesh", mesh_level_path)
        + level_full_xml(content_level_id, "character_art", content_level_path)
    )

    columns_xml = (
        mesh_column_xml(mesh_col_id, level_ref_xml(mesh_level_id), span=frame_count)
        + level_column_xml(content_col_id, level_ref_xml(content_level_id), span=frame_count)
    )

    # 2-bone skeleton: Root (parent None) -> Child.
    # Coordinates match build_mesh_file.py's mesh scale (a few field units -
    # this project's default camera is a 16x9 field; 100-unit coordinates
    # sit almost entirely outside it and render as empty frames).
    vertices = [
        {"name": "Root", "number": 1, "pos": (0.0, 0.0), "parent": None},
        {"name": "Child", "number": 2, "pos": (0.0, 5.0), "parent": 0},
    ]

    # >=3 keyframes on the Child vertex's Angle (bend) and Distance (stretch),
    # demonstrating the pose changing over time (frames 1, 12, 24 of a
    # 24-frame / 12fps ~2s clip).
    vertex_deforms = {
        "Root": {"hook": 1, "angle_keyframes": [], "distance_keyframes": []},
        "Child": {
            "hook": 2,
            "angle_keyframes": [(1, 0.0), (12, 45.0), (24, -30.0)],
            "distance_keyframes": [(1, 0.0), (12, 0.75), (24, 0.0)],
        },
    }

    plastic_sd = plastic_sd_xml(vertices, vertex_deforms)

    pegbars_xml = (
        pegbar_xml(f"Col{1}", parent_id="Table", plastic_sd=plastic_sd)
        + pegbar_xml(f"Col{2}", parent_id="Col1", handle="", parent_handle="")
    )

    xsheet_xml = (
        f"<columns>{columns_xml}</columns>"
        f"<pegbars>{pegbars_xml}</pegbars>"
    )

    tnz = (
        f'<tnz version="82.0" framecount="{frame_count}">'
        "<generator>OpenToonzPlasticPOC 1.0</generator>"
        f"<levelSet><levels>{levels_xml}</levels></levelSet>"
        f"<xsheet>{xsheet_xml}</xsheet>"
        "</tnz>"
    )
    return tnz


if __name__ == "__main__":
    import sys
    out_path = sys.argv[1] if len(sys.argv) > 1 else "output/poc_scene.tnz"
    mesh_rel = sys.argv[2] if len(sys.argv) > 2 else "character.mesh"
    content_rel = sys.argv[3] if len(sys.argv) > 3 else "character_art.png"
    frame_count = int(sys.argv[4]) if len(sys.argv) > 4 else 24

    xml_text = build_scene_xml(mesh_rel, content_rel, frame_count)
    with open(out_path, "w", encoding="ascii") as f:
        f.write(xml_text)
    print(f"wrote {out_path} ({len(xml_text)} bytes)")
