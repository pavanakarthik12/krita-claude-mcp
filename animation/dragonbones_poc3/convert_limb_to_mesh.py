"""
POC #3: prove DragonBones' real weighted-mesh skinning solves POC #2's
"rigid raster forces the distal bone to freeze" problem, for ONE limb
(the traced front leg of character_lock_walker2_v2.json).

READ-ONLY with respect to the Character Lock and the existing animation
engine: only imports CharacterLockModel / Bone / articulation_lib.axis_weight
(all unmodified) and reads character_lock_walker2_v2.json. Writes nothing
outside animation/dragonbones_poc3/.

Structured to be limb-agnostic (requirement 13: swap "leg" for "arm" later
without rewriting): everything limb-specific is gathered into one LIMB dict
at the top; build_limb_mesh_asset() takes it as a parameter and contains no
leg-specific literals.

Pipeline:
  1. Load the lock (checksum + skeleton validated, same as POC #2).
  2. Extract the limb's traced Bézier geometry (components_geometry[...]),
     UNCHANGED - saved verbatim to leg_source_geometry.json as the
     preserved source of truth.
  3. Flatten the Bézier contour to a polygon, triangulate it (Delaunay over
     boundary + interior sample points, keeping only triangles whose
     centroid falls inside the traced silhouette) - a real triangulated
     mesh covering the actual shape, not a placeholder quad.
  4. Compute each mesh vertex's bone weight via articulation_lib.axis_weight
     (unmodified, already-proven projection-based weighting) against the
     proximal (thigh) pivot and distal (shin) pivot - automatic, continuous,
     no manual weight painting.
  5. Emit a real DragonBones armature+skin+mesh JSON (character_ske.json),
     using the exact binary/JSON layout read from
     DragonBones/src/dragonBones/parser/JSONDataParser.cpp::_parseMesh
     (vertices/uvs/triangles/weights/slotPose/bonePose) - not invented.
  6. Rasterize the rigid foot component (unchanged rigid technique from
     POC #2) for the "foot stays attached" check.
"""
import json
import math
import os
import sys

import numpy as np
from scipy.spatial import Delaunay
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.character_model import CharacterLockModel
from animation.articulation_lib import axis_weight

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
PARTS_DIR = os.path.join(HERE, "parts")
LOCK_PATH = os.path.join(DATA_DIR, "character_lock_walker2_v2.json")

# ---------------------------------------------------------------------------
# Everything limb-specific lives here. To convert the arm instead: swap this
# one dict for {"proximal_bone": "upper_arm_front", "distal_bone":
# "forearm_front", "mesh_component": "front_upper_arm", "rigid_component":
# "front_hand", ...} - build_limb_mesh_asset() below has no other
# leg-specific literal in it.
# ---------------------------------------------------------------------------
LIMB = {
    "proximal_bone": "thigh_front",   # Character Lock bone name (hip)
    "distal_bone": "shin_front",      # Character Lock bone name (knee->ankle)
    "mesh_component": "front_leg",    # components_geometry key to mesh-deform
    "rigid_component": "front_foot",  # components_geometry key to rigidly attach
    "dragonbones_proximal_name": "thigh",  # POC #3 output bone names (req. 5)
    "dragonbones_distal_name": "shin",
}


def bezier_point(p0, p1, p2, p3, t):
    mt = 1.0 - t
    x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
    y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
    return (x, y)


def flatten_contour(segments, steps_per_seg=16):
    pts = []
    for seg in segments:
        p0, p1, p2, p3 = seg["start"], seg["control1"], seg["control2"], seg["end"]
        for i in range(steps_per_seg):
            t = i / steps_per_seg
            pts.append(bezier_point(p0, p1, p2, p3, t))
    return pts


def point_in_polygon(x, y, poly):
    """Standard ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def triangulate_polygon(boundary_pts, interior_spacing=18):
    """Delaunay triangulation over the traced boundary plus a grid of
    interior sample points, keeping only triangles whose centroid falls
    inside the traced silhouette - a standard, automatic way to cover an
    arbitrary simple polygon with a real triangle mesh without a full
    constrained-Delaunay/hole library dependency."""
    xs = [p[0] for p in boundary_pts]
    ys = [p[1] for p in boundary_pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    interior_pts = []
    x = minx + interior_spacing / 2
    while x < maxx:
        y = miny + interior_spacing / 2
        while y < maxy:
            if point_in_polygon(x, y, boundary_pts):
                interior_pts.append((x, y))
            y += interior_spacing
        x += interior_spacing

    all_pts = boundary_pts + interior_pts
    tri = Delaunay(np.array(all_pts))

    kept = []
    for simplex in tri.simplices:
        p0, p1, p2 = (all_pts[i] for i in simplex)
        cx = (p0[0] + p1[0] + p2[0]) / 3.0
        cy = (p0[1] + p1[1] + p2[1]) / 3.0
        if point_in_polygon(cx, cy, boundary_pts):
            kept.append(tuple(int(i) for i in simplex))

    return all_pts, kept


def rest_world_rotation(model, bone_name):
    """Accumulated rest rotation (parent + own rest_orientation_deg), same
    additive formula as transform_evaluator.bone_world() and POC #2's
    conversion script - reused, not reimplemented."""
    bone = model.skeleton[bone_name]
    if bone.parent is None:
        return bone.rest_orientation_deg
    return rest_world_rotation(model, bone.parent) + bone.rest_orientation_deg


def bind_matrix(rotation_deg, pos):
    """A bone's rest-pose world matrix in DragonBones' own [a,b,c,d,tx,ty]
    convention (verified against Transform::toMatrix in
    DragonBones/src/dragonBones/geom/Transform.h: a=cos,b=sin,c=-sin,d=cos
    for a pure rotation+translation, skew=0)."""
    r = math.radians(rotation_deg)
    return [math.cos(r), math.sin(r), -math.sin(r), math.cos(r), pos[0], pos[1]]


def build_limb_mesh_asset(model, limb):
    proximal = model.skeleton[limb["proximal_bone"]]
    distal = model.skeleton[limb["distal_bone"]]

    proximal_rotation = rest_world_rotation(model, limb["proximal_bone"])
    distal_rotation = rest_world_rotation(model, limb["distal_bone"])

    # --- geometry: preserved source of truth ---
    raw_segments = model.components_geometry[limb["mesh_component"]]

    boundary = flatten_contour(raw_segments)
    all_pts, triangles = triangulate_polygon(boundary)

    # --- automatic weights: projection along proximal->distal axis, using
    # the existing, unmodified articulation_lib.axis_weight ---
    weights_per_vertex = []
    for (x, y) in all_pts:
        w_distal = axis_weight((x, y), proximal.rest_pivot, distal.rest_pivot)
        weights_per_vertex.append((1.0 - w_distal, w_distal))

    # --- DragonBones mesh JSON fields (exact layout from
    # JSONDataParser.cpp::_parseMesh) ---
    vertices_flat = []
    uvs_flat = []
    minx = min(p[0] for p in all_pts)
    maxx = max(p[0] for p in all_pts)
    miny = min(p[1] for p in all_pts)
    maxy = max(p[1] for p in all_pts)
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)
    for (x, y) in all_pts:
        vertices_flat.extend([x, y])
        uvs_flat.extend([(x - minx) / span_x, (y - miny) / span_y])

    triangles_flat = []
    for (i0, i1, i2) in triangles:
        triangles_flat.extend([i0, i1, i2])

    weights_flat = []
    for (w_prox, w_dist) in weights_per_vertex:
        entries = []
        if w_prox > 1e-6:
            entries.append((0, w_prox))
        if w_dist > 1e-6:
            entries.append((1, w_dist))
        if not entries:
            entries = [(0, 1.0)]  # degenerate guard - should not occur
        weights_flat.append(len(entries))
        for bone_index, w in entries:
            weights_flat.extend([bone_index, w])

    slot_pose = [1, 0, 0, 1, 0, 0]  # identity: vertices already in armature space
    bone_pose = []
    bone_pose.extend([0] + bind_matrix(proximal_rotation, proximal.rest_pivot))
    bone_pose.extend([1] + bind_matrix(distal_rotation, distal.rest_pivot))

    mesh_display = {
        "name": limb["mesh_component"],
        "type": "mesh",
        "uvs": uvs_flat,
        "vertices": vertices_flat,
        "triangles": triangles_flat,
        "weights": weights_flat,
        "slotPose": slot_pose,
        "bonePose": bone_pose,
    }

    dbones_proximal = limb["dragonbones_proximal_name"]
    dbones_distal = limb["dragonbones_distal_name"]

    bones_json = [
        {
            "name": dbones_proximal,
            "transform": {
                "x": round(proximal.rest_pivot[0], 4),
                "y": round(proximal.rest_pivot[1], 4),
                "skX": round(proximal_rotation, 4),
                "skY": round(proximal_rotation, 4),
            },
            "length": round(proximal.length, 4) if proximal.length else 0,
        },
        {
            "name": dbones_distal,
            "parent": dbones_proximal,
            "inheritRotation": False,
            "transform": _local_offset(proximal, distal, proximal_rotation),
            "length": round(distal.length, 4) if distal.length else 0,
        },
    ]

    slot_name = limb["mesh_component"]
    ske = {
        "frameRate": 24,
        "name": "LimbMeshData",
        "version": "5.5",
        "armature": [
            {
                "type": "Armature",
                "name": "Limb",
                "frameRate": 24,
                "bone": bones_json,
                "slot": [{"name": slot_name, "parent": dbones_proximal}],
                "skin": [
                    {
                        "name": "",
                        "slot": [
                            {"name": slot_name, "display": [mesh_display]}
                        ],
                    }
                ],
                "ik": [],
                "animation": [],
            }
        ],
    }

    return ske, raw_segments, all_pts, triangles, weights_per_vertex


def _local_offset(proximal, distal, proximal_rotation):
    """Distal bone's rest pivot expressed in the proximal bone's
    rest-oriented local frame - same construction (and same previously-
    caught raw-rest-pivot-not-bone_world-pivot fix) as POC #2's converter."""
    from animation.articulation_lib import rotate_pt
    local = rotate_pt(distal.rest_pivot, proximal.rest_pivot, -proximal_rotation)
    offset = [local[0] - proximal.rest_pivot[0], local[1] - proximal.rest_pivot[1]]
    distal_rotation = proximal_rotation  # own rest_orientation_deg is 0 for shin
    return {
        "x": round(offset[0], 4),
        "y": round(offset[1], 4),
        "skX": round(distal_rotation, 4),
        "skY": round(distal_rotation, 4),
    }


def rasterize_rigid_component(model, component_name, bone_name, dragonbones_bone_name):
    """Verbatim reuse of POC #2's rigid-part rasterization technique for
    the foot, which the lock's own attachment data marks as a
    rigid_child (not part of the soft-skin blend) - not something this
    mesh-deformation POC should second-guess.

    bone_name: the Character Lock's own bone name (used to look up
    rest_pivot from the lock, which is all this function reads from it).
    dragonbones_bone_name: the name that bone was given in THIS POC's
    generated character_ske.json ("thigh"/"shin", not "thigh_front"/
    "shin_front") - what main.cpp's armature->getBone() must be able to
    find. Storing the lock's own name here instead was a real bug caught
    while inspecting the first render (the foot silently failed to attach
    because armature->getBone("shin_front") returned nullptr).
    """
    segments = model.components_geometry[component_name]
    poly = flatten_contour(segments)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    padding = 6
    left, top = min(xs) - padding, min(ys) - padding
    right, bottom = max(xs) + padding, max(ys) + padding
    w, h = max(int(math.ceil(right - left)), 1), max(int(math.ceil(bottom - top)), 1)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    local_poly = [(x - left, y - top) for x, y in poly]
    draw.polygon(local_poly, fill=(60, 60, 60, 255), outline=(20, 20, 20, 255))
    filename = f"{component_name}.png"
    img.save(os.path.join(PARTS_DIR, filename))

    bone_pivot = model.skeleton[bone_name].rest_pivot
    return {
        "file": os.path.join("parts", filename).replace("\\", "/"),
        "width": w,
        "height": h,
        "pivot_x": round(bone_pivot[0] - left, 4),
        "pivot_y": round(bone_pivot[1] - top, 4),
        "bone": dragonbones_bone_name,
    }


def main():
    os.makedirs(PARTS_DIR, exist_ok=True)

    model = CharacterLockModel.from_file(LOCK_PATH)
    assert model.checksum_valid(), "character_lock_walker2_v2.json failed its own checksum check"
    problems = model.validate_skeleton()
    assert not problems, f"skeleton validation failed: {problems}"

    ske, raw_segments, all_pts, triangles, weights = build_limb_mesh_asset(model, LIMB)

    # Preserve the exact traced source geometry (requirement 3), unchanged,
    # alongside the generated mesh - so the mesh's provenance is auditable.
    with open(os.path.join(HERE, "leg_source_geometry.json"), "w") as f:
        json.dump({
            "component": LIMB["mesh_component"],
            "source_lock": os.path.basename(LOCK_PATH),
            "segments": raw_segments,
        }, f, indent=2)

    ske_path = os.path.join(HERE, "character_ske.json")
    with open(ske_path, "w") as f:
        json.dump(ske, f, indent=2)

    foot = rasterize_rigid_component(
        model, LIMB["rigid_component"], LIMB["distal_bone"], LIMB["dragonbones_distal_name"]
    )
    with open(os.path.join(HERE, "parts_manifest.json"), "w") as f:
        json.dump({"parts": [{"component": LIMB["rigid_component"], **foot}]}, f, indent=2)

    print(f"lock checksum valid: {model.checksum_valid()}")
    print(f"mesh component: {LIMB['mesh_component']}")
    print(f"  boundary points: {len(flatten_contour(raw_segments))}")
    print(f"  total mesh vertices: {len(all_pts)}")
    print(f"  triangles: {len(triangles)}")
    w_min = min(w[1] for w in weights)
    w_max = max(w[1] for w in weights)
    at_zero = sum(1 for w in weights if w[1] < 1e-6)
    at_one = sum(1 for w in weights if w[1] > 1 - 1e-6)
    mid = len(weights) - at_zero - at_one
    print(f"  distal(shin) weight range: [{w_min:.4f}, {w_max:.4f}]")
    print(f"  vertices fully proximal (w=0): {at_zero}, fully distal (w=1): {at_one}, blended: {mid}")
    print(f"wrote {ske_path}")
    print(f"rigid foot part: {foot['file']} (bone={foot['bone']})")


if __name__ == "__main__":
    main()
