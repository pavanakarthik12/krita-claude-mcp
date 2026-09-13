"""
POC #2: Character Lock -> DragonBones asset conversion.

READ-ONLY with respect to the existing animation engine and Character Lock
files: this script only *imports* CharacterLockModel / TransformEvaluator /
rotate_pt (unmodified) and *reads* character_lock_walker2_v2.json. It writes
nothing back to animation/data/ and nothing outside animation/dragonbones_poc/.

Two outputs, both DragonBones-consumable / POC-consumable:

  character_ske.json   - a real DragonBones skeleton JSON (bone hierarchy,
                          name/parent/rest pivot/rest orientation/length),
                          built the same way animation/transform_evaluator.py
                          already knows how to compute rest world transforms
                          (bone_world() at an all-zero Pose) - reused here,
                          not reimplemented.

  parts/*.png + parts_manifest.json
                        - one rasterized PNG per traced Bézier component
                          (rigid cutout part - no weighted mesh deformation,
                          per this POC's explicit scope), plus the bone each
                          part is rigidly bound to and its pivot-in-image
                          offset, for the C++ renderer to place/rotate it.

DragonBones bone-transform convention used (matches the already-proven
DragonBonesCPP/poc/character_ske.json pattern - see that POC's README,
"How the bones are controlled"):
  - every non-root bone gets "inheritRotation": false. Its "skX"/"skY" store
    the bone's REST WORLD rotation (preserved from the lock); at animation
    time the renderer writes only the POSE DELTA into bone->offset.rotation.
    Since inheritRotation is false, DragonBones does not add the parent's
    rotation again, so global rotation = rest (baked into transform) + delta
    (written each frame) - exactly what's needed to preserve rest orientation
    while still allowing procedural animation on top.
  - "transform.x/y" for a non-root bone is the child's rest pivot expressed
    in the PARENT's rest-oriented LOCAL frame (rotate the world rest offset
    by -parent_world_rotation) - because DragonBones re-applies the parent's
    current (rest+delta) world rotation to this offset when composing
    position, mirroring transform_evaluator.bone_world()'s own
    parent-rotates-child-offset formula exactly.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.character_model import CharacterLockModel
from animation.transform_evaluator import TransformEvaluator
from animation.articulation_lib import rotate_pt

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
PARTS_DIR = os.path.join(HERE, "parts")

LOCK_PATH = os.path.join(DATA_DIR, "character_lock_walker2_v2.json")

# Which bone each traced component is RIGIDLY bound to for this POC (no
# soft-skin blending - explicitly out of scope). Proximal components ride
# the proximal bone of their attachment; rigid_children ride the distal
# bone, exactly as the lock's own "attachments" already specify.
COMPONENT_TO_BONE = {
    "head": "head",
    "torso": "torso",
    "front_upper_arm": "upper_arm_front",
    "front_hand": "forearm_front",
    "back_upper_arm": "upper_arm_back",
    "back_hand": "forearm_back",
    "front_leg": "thigh_front",
    "front_foot": "shin_front",
    "back_leg": "thigh_back",
    "back_foot": "shin_back",
}

# Back-to-front draw order for a side-view character (POC only - no attempt
# at correctness beyond "arms/legs don't obviously draw in front of the
# wrong thing").
DRAW_ORDER = [
    "back_leg", "back_foot", "back_upper_arm", "back_hand",
    "torso",
    "front_leg", "front_foot", "front_upper_arm", "front_hand",
    "head",
]

PADDING = 6  # px around each component's bbox in its rasterized PNG


def bezier_point(p0, p1, p2, p3, t):
    mt = 1.0 - t
    x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
    y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
    return (x, y)


def sample_component_polygon(segments, steps_per_seg=14):
    """Flattens a list of cubic-Bezier segments (start/control1/control2/end)
    - as stored verbatim in components_geometry - into a closed polygon."""
    pts = []
    for seg in segments:
        p0, p1, p2, p3 = seg["start"], seg["control1"], seg["control2"], seg["end"]
        for i in range(steps_per_seg):
            t = i / steps_per_seg
            pts.append(bezier_point(p0, p1, p2, p3, t))
    return pts


# A distinct fill color per component, purely for POC visibility/debugging -
# not derived from the Character Lock (which has no color data at this
# stage of the pipeline).
COMPONENT_COLORS = {
    "head": (235, 200, 170, 255),
    "torso": (110, 130, 170, 255),
    "front_upper_arm": (150, 170, 120, 255),
    "front_hand": (200, 190, 150, 255),
    "back_upper_arm": (170, 140, 120, 255),
    "back_hand": (200, 170, 140, 255),
    "front_leg": (90, 110, 150, 255),
    "front_foot": (60, 60, 60, 255),
    "back_leg": (140, 100, 100, 255),
    "back_foot": (60, 60, 60, 255),
}


def rasterize_component(name, segments):
    poly = sample_component_polygon(segments)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    left, top = min(xs) - PADDING, min(ys) - PADDING
    right, bottom = max(xs) + PADDING, max(ys) + PADDING
    w, h = int(math.ceil(right - left)), int(math.ceil(bottom - top))
    w, h = max(w, 1), max(h, 1)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    local_poly = [(x - left, y - top) for x, y in poly]
    color = COMPONENT_COLORS.get(name, (180, 180, 180, 255))
    draw.polygon(local_poly, fill=color, outline=(30, 30, 30, 255))

    filename = f"{name}.png"
    img.save(os.path.join(PARTS_DIR, filename))
    return {
        "file": filename,
        "width": w,
        "height": h,
        "bbox_left": left,
        "bbox_top": top,
    }


def build_rest_world_rotations(model):
    """Each bone's accumulated REST rotation (parent rotation + this bone's
    own rest_orientation_deg, per transform_evaluator.bone_world()'s own
    additive formula - reused, not reimplemented). Pure angle bookkeeping,
    no geometry/pivot involved, so it carries no risk of the pivot
    discrepancy documented below.
    """
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


def build_bone_json(model, rest_rotation):
    """Returns the DragonBones "bone" array, walking the lock's own
    hierarchy (root_bones()/children_of(), unmodified) rather than assuming
    an order, so this works for any lock with an arbitrary-depth skeleton,
    not just walker2's specific 11 bones.

    IMPORTANT: bone POSITIONS here use each bone's own raw `rest_pivot`
    (the traced pixel position stored in the lock) directly, NOT
    TransformEvaluator.bone_world()'s recomposed pivot. Verified by direct
    computation (see conversation record) that for a bone like
    "shin_back" - whose parent "thigh_back" has a non-zero
    rest_orientation_deg - bone_world()'s parent-rotates-child-rest-offset
    formula does NOT reproduce that bone's own raw rest_pivot (a ~50px
    discrepancy for shin_back). That formula is correct and necessary for
    composing a POSED chain (transform_evaluator's actual job), but using
    its REST-pose pivot output here would place the DragonBones bone (and
    this POC's rigid raster part) at a position that does not match where
    the component's Bézier points were actually traced, producing a visible
    seam. Using bone.rest_pivot directly, with the local offset derived by
    rotating the RAW parent-child pivot difference by the parent's
    accumulated rest rotation, was verified to round-trip back to the
    exact raw rest_pivot when DragonBones recomposes the hierarchy at rest
    (offset=0) - i.e. it reproduces the locked geometry unchanged, exactly
    as required.
    """
    bones_json = []

    def visit(bone_name):
        bone = model.skeleton[bone_name]
        pivot = bone.rest_pivot
        rotation_deg = rest_rotation[bone_name]

        entry = {"name": bone_name}
        if bone.parent is not None:
            entry["parent"] = bone.parent
            parent_pivot = model.skeleton[bone.parent].rest_pivot
            parent_rotation = rest_rotation[bone.parent]
            # child's rest pivot expressed in the parent's rest-oriented
            # local frame (inverse of the rotation transform_evaluator
            # applies when composing a posed child's world pivot).
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
            entry["transform"] = {
                "x": round(pivot[0], 4),
                "y": round(pivot[1], 4),
            }
        if bone.length is not None:
            entry["length"] = round(bone.length, 4)

        bones_json.append(entry)
        for child in sorted(model.children_of(bone_name), key=lambda b: b.name):
            visit(child.name)

    for root in model.root_bones():
        visit(root.name)

    return bones_json


def main():
    os.makedirs(PARTS_DIR, exist_ok=True)

    model = CharacterLockModel.from_file(LOCK_PATH)

    # --- integrity: the lock is the authoritative source of truth; refuse
    # to proceed from a lock whose own checksum doesn't validate. ---
    assert model.checksum_valid(), "character_lock_walker2_v2.json failed its own checksum check"
    problems = model.validate_skeleton()
    assert not problems, f"skeleton validation failed: {problems}"

    # TransformEvaluator itself is unused for position math in this POC (see
    # build_bone_json's docstring for why: its bone_world() pivot recomposition
    # is for POSED-chain geometry dispatch, not a rest-pose position source).
    # Imported and instantiated anyway to prove the existing, unmodified
    # evaluator loads and runs cleanly against this lock, and to make the
    # avoided pitfall an explicit, checkable fact rather than an assumption.
    evaluator = TransformEvaluator(model)
    _sanity_pivot, _sanity_rot, _ = evaluator.bone_world("root", {})
    assert list(_sanity_pivot) == list(model.skeleton["root"].rest_pivot)

    rest_rotation = build_rest_world_rotations(model)
    bones_json = build_bone_json(model, rest_rotation)

    ske = {
        "frameRate": 24,
        "name": "Walker2Data",
        "version": "5.5",
        "armature": [
            {
                "type": "Armature",
                "name": "Walker2",
                "frameRate": 24,
                "bone": bones_json,
                "skin": [],
                "ik": [],
                "animation": [],
            }
        ],
    }

    ske_path = os.path.join(HERE, "character_ske.json")
    with open(ske_path, "w") as f:
        json.dump(ske, f, indent=2)
    print(f"wrote {ske_path} ({len(bones_json)} bones)")

    manifest = {"parts": []}
    for comp_name, geom in model.components_geometry.items():
        bone_name = COMPONENT_TO_BONE[comp_name]
        raster = rasterize_component(comp_name, geom)
        bone_pivot = model.skeleton[bone_name].rest_pivot
        pivot_in_image = [
            bone_pivot[0] - raster["bbox_left"],
            bone_pivot[1] - raster["bbox_top"],
        ]
        manifest["parts"].append({
            "component": comp_name,
            "bone": bone_name,
            "file": os.path.join("parts", raster["file"]).replace("\\", "/"),
            "width": raster["width"],
            "height": raster["height"],
            "pivot_x": round(pivot_in_image[0], 4),
            "pivot_y": round(pivot_in_image[1], 4),
        })
        print(f"  rasterized {comp_name:16s} -> {raster['file']:20s} "
              f"{raster['width']}x{raster['height']}  bone={bone_name}")

    order_index = {name: i for i, name in enumerate(DRAW_ORDER)}
    manifest["parts"].sort(key=lambda p: order_index.get(p["component"], 999))

    manifest_path = os.path.join(HERE, "parts_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"wrote {manifest_path} ({len(manifest['parts'])} parts)")

    print(f"\nsource lock: {LOCK_PATH}")
    print(f"lock checksum valid: {model.checksum_valid()}")
    print(f"lock character_id: {model.character_id}")


if __name__ == "__main__":
    main()
