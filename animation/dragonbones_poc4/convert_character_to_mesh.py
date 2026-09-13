"""
POC #4: ONE combined DragonBones character asset from the walker2 Character
Lock - full skeleton (all bones), four weighted-mesh limbs (front/back leg,
front/back arm), six rigid parts (head, torso, front/back hand, front/back
foot), all in a SINGLE shared armature.

READ-ONLY with respect to the Character Lock and the existing animation
engine: only imports CharacterLockModel / Bone / Attachment /
articulation_lib.axis_weight / rotate_pt (all unmodified) and reads
character_lock_walker2_v2.json. Writes nothing outside
animation/dragonbones_poc4/.

Does NOT invent a new character model: the skeleton hierarchy and which
bones/geometry belong to which attachment are read directly from the lock's
own `model.skeleton` / `model.attachments` (Bone/Attachment objects from
animation/bone.py), generalizing POC #2's bone-conversion function and
POC #3's mesh-conversion function to iterate over the lock's own data
instead of a single hardcoded limb.

Every attachment with strategy == "soft_skin_2joint" becomes a real
DragonBones weighted mesh (proven in POC #3). Every attachment with
strategy == "rigid" (head, torso), and every rigid_children entry within a
soft_skin_2joint attachment (hands, feet), is rasterized as a rigid part
using POC #2's technique, exactly matching what the lock's own data says is
rigid - nothing is deformed that the lock doesn't mark as a two-bone blend.
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
from animation.articulation_lib import axis_weight, rotate_pt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
PARTS_DIR = os.path.join(HERE, "parts")
LOCK_PATH = os.path.join(DATA_DIR, "character_lock_walker2_v2.json")


# ---------------------------------------------------------------------------
# Geometry helpers (same technique as POC #2 / POC #3, unchanged)
# ---------------------------------------------------------------------------

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


def bind_matrix(rotation_deg, pos):
    r = math.radians(rotation_deg)
    return [math.cos(r), math.sin(r), -math.sin(r), math.cos(r), pos[0], pos[1]]


# ---------------------------------------------------------------------------
# Skeleton conversion (generalizes POC #2's build_bone_json: walk the lock's
# OWN hierarchy via root_bones()/children_of(), use each bone's raw
# rest_pivot - not TransformEvaluator.bone_world()'s posed-chain pivot, per
# the discrepancy caught and fixed during POC #2 - see that POC's report)
# ---------------------------------------------------------------------------

def build_rest_world_rotations(model):
    rotations = {}

    def visit(bone_name):
        bone = model.skeleton[bone_name]
        if bone.parent is None:
            rotations[bone_name] = bone.rest_orientation_deg
        else:
            if bone.parent not in rotations:
                visit(bone.parent)
            rotations[bone_name] = rotations[bone.parent] + bone.rest_orientation_deg

    for name in model.skeleton:
        visit(name)
    return rotations


def build_bones_json(model, rest_rotation):
    """Returns (bones_json, bone_order) where bone_order[name] = index in
    the emitted "bone" array - needed later so each mesh's bonePose can
    reference the correct SHARED armature bone index."""
    bones_json = []
    bone_order = {}

    def visit(bone_name):
        bone = model.skeleton[bone_name]
        pivot = bone.rest_pivot
        rotation_deg = rest_rotation[bone_name]

        entry = {"name": bone_name}
        if bone.parent is not None:
            entry["parent"] = bone.parent
            parent_pivot = model.skeleton[bone.parent].rest_pivot
            parent_rotation = rest_rotation[bone.parent]
            local = rotate_pt(pivot, parent_pivot, -parent_rotation)
            local_offset = [local[0] - parent_pivot[0], local[1] - parent_pivot[1]]
            entry["inheritRotation"] = False
            entry["transform"] = {
                "x": round(local_offset[0], 4),
                "y": round(local_offset[1], 4),
                "skX": round(rotation_deg, 4),
                "skY": round(rotation_deg, 4),
            }
        else:
            entry["transform"] = {"x": round(pivot[0], 4), "y": round(pivot[1], 4)}
        if bone.length is not None:
            entry["length"] = round(bone.length, 4)

        bone_order[bone_name] = len(bones_json)
        bones_json.append(entry)
        for child in sorted(model.children_of(bone_name), key=lambda b: b.name):
            visit(child.name)

    for root in model.root_bones():
        visit(root.name)

    return bones_json, bone_order


# ---------------------------------------------------------------------------
# One weighted mesh display, for one soft_skin_2joint attachment
# (generalizes POC #3's build_limb_mesh_asset)
# ---------------------------------------------------------------------------

def build_mesh_display(model, rest_rotation, bone_order, attachment_name, geometry_key):
    attachment = model.attachments[attachment_name]
    proximal_name, distal_name = attachment.bones
    proximal = model.skeleton[proximal_name]
    distal = model.skeleton[distal_name]

    raw_segments = model.components_geometry[geometry_key]
    boundary = flatten_contour(raw_segments)
    all_pts, triangles = triangulate_polygon(boundary)

    weights_per_vertex = []
    for (x, y) in all_pts:
        w_distal = axis_weight((x, y), proximal.rest_pivot, distal.rest_pivot)
        weights_per_vertex.append((1.0 - w_distal, w_distal))

    vertices_flat, uvs_flat = [], []
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)
    for (x, y) in all_pts:
        vertices_flat.extend([x, y])
        uvs_flat.extend([(x - minx) / span_x, (y - miny) / span_y])

    triangles_flat = []
    for (i0, i1, i2) in triangles:
        triangles_flat.extend([i0, i1, i2])

    proximal_idx = bone_order[proximal_name]
    distal_idx = bone_order[distal_name]

    weights_flat = []
    for (w_prox, w_dist) in weights_per_vertex:
        entries = []
        if w_prox > 1e-6:
            entries.append((proximal_idx, w_prox))
        if w_dist > 1e-6:
            entries.append((distal_idx, w_dist))
        if not entries:
            entries = [(proximal_idx, 1.0)]
        weights_flat.append(len(entries))
        for bone_index, w in entries:
            weights_flat.extend([bone_index, w])

    slot_pose = [1, 0, 0, 1, 0, 0]
    bone_pose = []
    bone_pose.extend([proximal_idx] + bind_matrix(rest_rotation[proximal_name], proximal.rest_pivot))
    bone_pose.extend([distal_idx] + bind_matrix(rest_rotation[distal_name], distal.rest_pivot))

    mesh_display = {
        "name": geometry_key,
        "type": "mesh",
        "uvs": uvs_flat,
        "vertices": vertices_flat,
        "triangles": triangles_flat,
        "weights": weights_flat,
        "slotPose": slot_pose,
        "bonePose": bone_pose,
    }

    stats = {
        "attachment": attachment_name,
        "geometry": geometry_key,
        "proximal_bone": proximal_name,
        "distal_bone": distal_name,
        "vertex_count": len(all_pts),
        "triangle_count": len(triangles),
        "weight_min": min(w[1] for w in weights_per_vertex),
        "weight_max": max(w[1] for w in weights_per_vertex),
        "blended_count": sum(1 for w in weights_per_vertex if 1e-6 < w[1] < 1 - 1e-6),
    }

    return mesh_display, proximal_name, stats


def rasterize_rigid_component(model, component_name, bone_name):
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
    color = RIGID_COLORS.get(component_name, (150, 150, 150, 255))
    draw.polygon(local_poly, fill=color, outline=(30, 30, 30, 255))
    filename = f"{component_name}.png"
    img.save(os.path.join(PARTS_DIR, filename))

    bone_pivot = model.skeleton[bone_name].rest_pivot
    return {
        "component": component_name,
        "bone": bone_name,
        "file": os.path.join("parts", filename).replace("\\", "/"),
        "width": w,
        "height": h,
        "pivot_x": round(bone_pivot[0] - left, 4),
        "pivot_y": round(bone_pivot[1] - top, 4),
    }


RIGID_COLORS = {
    "head": (235, 200, 170, 255),
    "torso": (110, 130, 170, 255),
    "front_hand": (200, 190, 150, 255),
    "back_hand": (200, 170, 140, 255),
    "front_foot": (40, 40, 40, 255),
    "back_foot": (40, 40, 40, 255),
}

MESH_COLORS = {
    "front_leg": (90, 110, 150, 255),
    "back_leg": (140, 100, 100, 255),
    "front_upper_arm": (150, 170, 120, 255),
    "back_upper_arm": (170, 140, 120, 255),
}


def main():
    os.makedirs(PARTS_DIR, exist_ok=True)

    model = CharacterLockModel.from_file(LOCK_PATH)
    assert model.checksum_valid(), "character_lock_walker2_v2.json failed its own checksum check"
    problems = model.validate_skeleton()
    assert not problems, f"skeleton validation failed: {problems}"

    rest_rotation = build_rest_world_rotations(model)
    bones_json, bone_order = build_bones_json(model, rest_rotation)

    mesh_displays = []       # (attachment_name, geometry_key, mesh_display_json, proximal_bone)
    rigid_parts = []
    mesh_stats = []

    for attachment_name, attachment in model.attachments.items():
        if attachment.strategy == "soft_skin_2joint":
            for geometry_key in attachment.geometry:
                mesh_display, proximal_bone, stats = build_mesh_display(
                    model, rest_rotation, bone_order, attachment_name, geometry_key
                )
                mesh_displays.append((attachment_name, geometry_key, mesh_display, proximal_bone))
                mesh_stats.append(stats)
            for geom_key, rigid_bone in attachment.rigid_children.items():
                rigid_parts.append(rasterize_rigid_component(model, geom_key, rigid_bone))
        elif attachment.strategy == "rigid":
            bone_name = attachment.bones[0]
            for geometry_key in attachment.geometry:
                rigid_parts.append(rasterize_rigid_component(model, geometry_key, bone_name))
        else:
            raise ValueError(f"unknown strategy '{attachment.strategy}' on attachment '{attachment_name}'")

    # --- ONE shared armature: all bones, one slot+skin entry per mesh ---
    slots_json = [{"name": geom_key, "parent": proximal_bone} for (_a, geom_key, _m, proximal_bone) in mesh_displays]
    skin_slots_json = [{"name": geom_key, "display": [mesh_display]} for (_a, geom_key, mesh_display, _p) in mesh_displays]

    ske = {
        "frameRate": 24,
        "name": "Walker2CharacterData",
        "version": "5.5",
        "armature": [
            {
                "type": "Armature",
                "name": "Walker2Character",
                "frameRate": 24,
                "bone": bones_json,
                "slot": slots_json,
                "skin": [{"name": "", "slot": skin_slots_json}],
                "ik": [],
                "animation": [],
            }
        ],
    }

    ske_path = os.path.join(HERE, "character_ske.json")
    with open(ske_path, "w") as f:
        json.dump(ske, f, indent=2)

    with open(os.path.join(HERE, "parts_manifest.json"), "w") as f:
        json.dump({"parts": rigid_parts}, f, indent=2)

    with open(os.path.join(HERE, "bone_order.json"), "w") as f:
        json.dump(bone_order, f, indent=2)

    # Preserve the exact traced source geometry for every mesh-deformed
    # component, unchanged, for provenance (requirement: preserve original
    # Bezier geometry as source of truth).
    source_geometry = {
        geom_key: model.components_geometry[geom_key] for (_a, geom_key, _m, _p) in mesh_displays
    }
    with open(os.path.join(HERE, "limb_source_geometry.json"), "w") as f:
        json.dump(source_geometry, f, indent=2)

    print(f"lock checksum valid: {model.checksum_valid()}")
    print(f"bones: {len(bones_json)} -> {list(bone_order.keys())}")
    print(f"mesh slots: {len(mesh_displays)}")
    for s in mesh_stats:
        print(f"  {s['attachment']:10s} geom={s['geometry']:16s} bones=({s['proximal_bone']},{s['distal_bone']}) "
              f"verts={s['vertex_count']:4d} tris={s['triangle_count']:4d} "
              f"weight_range=[{s['weight_min']:.3f},{s['weight_max']:.3f}] blended={s['blended_count']}")
    print(f"rigid parts: {len(rigid_parts)} -> {[p['component'] for p in rigid_parts]}")
    print(f"wrote {ske_path}")


if __name__ == "__main__":
    main()
