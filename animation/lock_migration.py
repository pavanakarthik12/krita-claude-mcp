"""
Builds the Phase 1 schema additions (skeleton / attachments / heading /
views) ON TOP OF the existing, unmodified character_lock_*.json data.

Every number used here is either already present in the source lock
(pivots_px) or trivially derivable from components_geometry (farthest
point from a pivot, a centroid) using the exact same techniques
walker2_build_lock.py / walker2_animate_articulated.py already used ad
hoc. No new measurement/tracing logic is introduced, and the ORIGINAL
geometry is never altered - this module only ADDS keys to a copy of the
loaded dict and writes that to a new file.

walker2 (character_lock_walker2.json) is the primary, fully-conformant
migration: its existing shape already has every field name this phase's
schema expects (components_geometry, checksum, pivots_px, hierarchy,
measurements, ratios).

The hat/shirt character's actual full geometry lives in a differently-
shaped file (character_model_hatshirt.json, from the earlier Part 6/7
work) rather than in character_lock_hatshirt.json (which is a thin
wrapper - checksum + validated ratios only, no geometry). This module
normalizes that older shape into the same target schema; see
migrate_hatshirt()'s docstring for exactly what is reported as an
inferred/ambiguous mapping decision rather than a direct field copy.
"""
import hashlib
import json
import math
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _rest_angle_deg(pivot, tip):
    """The angle that rotate_pt would need to apply to (0, |tip-pivot|)
    (straight down from pivot) to land exactly on tip - i.e. this
    geometry's own inherent rest angle, in the SAME sign convention
    articulation_lib.rotate_pt already uses. Derived once here from
    existing pivot/tip data, matching the atan2(-dx, dy) formula already
    used (and verified) in the walker2 rig-correction work."""
    dx = tip[0] - pivot[0]
    dy = tip[1] - pivot[1]
    return math.degrees(math.atan2(-dx, dy))


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _all_points(segs):
    pts = []
    for seg in segs:
        pts.append(seg["start"])
        pts.append(seg["end"])
    return pts


def _farthest_point(segs, pivot):
    pts = _all_points(segs)
    best, best_d = pts[0], -1.0
    for p in pts:
        d = _dist(p, pivot)
        if d > best_d:
            best, best_d = p, d
    return best


def _centroid(segs):
    pts = _all_points(segs)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


# ---------------------------------------------------------------------------
# walker2: primary, fully-conformant migration
# ---------------------------------------------------------------------------
def migrate_walker2(source_path=None, dest_path=None):
    source_path = source_path or os.path.join(DATA_DIR, "character_lock_walker2.json")
    dest_path = dest_path or os.path.join(DATA_DIR, "character_lock_walker2_v2.json")

    with open(source_path) as f:
        lock = json.load(f)
    comps = lock["components_geometry"]
    pivots = lock["pivots_px"]

    # Rest angles + tip/joint points, reusing exactly the pivots already
    # stored in pivots_px and the farthest-point technique already used.
    limb_geom = {
        "front_arm": "front_upper_arm", "back_arm": "back_upper_arm",
        "front_leg": "front_leg", "back_leg": "back_leg",
    }
    tips, joints, rest_angles = {}, {}, {}
    for limb, geom_key in limb_geom.items():
        pivot = pivots[limb]
        tip = _farthest_point(comps[geom_key], pivot)
        tips[limb] = tip
        joints[limb] = [(pivot[0] + tip[0]) / 2.0, (pivot[1] + tip[1]) / 2.0]
        rest_angles[limb] = _rest_angle_deg(pivot, tip)

    root_pivot = [(pivots["front_leg"][0] + pivots["back_leg"][0]) / 2.0,
                  (pivots["front_leg"][1] + pivots["back_leg"][1]) / 2.0]
    torso_pivot = _centroid(comps["torso"])
    head_pivot = _centroid(comps["head"])

    def bone(parent, rest_pivot, rest_orientation_deg=0.0, length=None, strategy="rigid"):
        return {"parent": parent, "rest_pivot": list(rest_pivot),
                "rest_orientation_deg": rest_orientation_deg, "length": length,
                "transform_strategy": strategy}

    skeleton = {
        "root": {"parent": None, "rest_pivot": root_pivot, "rest_orientation_deg": 0.0, "length": None},
        "torso": bone("root", torso_pivot, 0.0, _dist(torso_pivot, root_pivot)),
        "head": bone("torso", head_pivot, 0.0, _dist(head_pivot, torso_pivot)),
    }
    skeleton["upper_arm_front"] = bone("torso", pivots["front_arm"], rest_angles["front_arm"],
                                        _dist(pivots["front_arm"], torso_pivot), "soft_skin_2joint")
    skeleton["forearm_front"] = bone("upper_arm_front", joints["front_arm"], 0.0,
                                      _dist(joints["front_arm"], pivots["front_arm"]), "soft_skin_2joint")
    skeleton["upper_arm_back"] = bone("torso", pivots["back_arm"], rest_angles["back_arm"],
                                       _dist(pivots["back_arm"], torso_pivot), "soft_skin_2joint")
    skeleton["forearm_back"] = bone("upper_arm_back", joints["back_arm"], 0.0,
                                     _dist(joints["back_arm"], pivots["back_arm"]), "soft_skin_2joint")
    skeleton["thigh_front"] = bone("torso", pivots["front_leg"], rest_angles["front_leg"],
                                    _dist(pivots["front_leg"], torso_pivot), "soft_skin_2joint")
    skeleton["shin_front"] = bone("thigh_front", joints["front_leg"], 0.0,
                                   _dist(joints["front_leg"], pivots["front_leg"]), "soft_skin_2joint")
    skeleton["thigh_back"] = bone("torso", pivots["back_leg"], rest_angles["back_leg"],
                                   _dist(pivots["back_leg"], torso_pivot), "soft_skin_2joint")
    skeleton["shin_back"] = bone("thigh_back", joints["back_leg"], 0.0,
                                  _dist(joints["back_leg"], pivots["back_leg"]), "soft_skin_2joint")

    attachments = {
        "head": {"bones": ["head"], "strategy": "rigid", "geometry": ["head"], "rigid_children": {}},
        "torso": {"bones": ["torso"], "strategy": "rigid", "geometry": ["torso"], "rigid_children": {}},
        "front_arm": {"bones": ["upper_arm_front", "forearm_front"], "strategy": "soft_skin_2joint",
                      "geometry": ["front_upper_arm"], "rigid_children": {"front_hand": "forearm_front"}},
        "back_arm": {"bones": ["upper_arm_back", "forearm_back"], "strategy": "soft_skin_2joint",
                     "geometry": ["back_upper_arm"], "rigid_children": {"back_hand": "forearm_back"}},
        "front_leg": {"bones": ["thigh_front", "shin_front"], "strategy": "soft_skin_2joint",
                      "geometry": ["front_leg"], "rigid_children": {"front_foot": "shin_front"}},
        "back_leg": {"bones": ["thigh_back", "shin_back"], "strategy": "soft_skin_2joint",
                     "geometry": ["back_leg"], "rigid_children": {"back_foot": "shin_back"}},
    }

    lock["skeleton"] = skeleton
    lock["attachments"] = attachments
    lock["heading"] = {"rest_facing": "right"}
    lock["views"] = {"side": {"components_geometry": "components_geometry", "skeleton": "skeleton"}}

    with open(dest_path, "w") as f:
        json.dump(lock, f, indent=1)
    return dest_path


# ---------------------------------------------------------------------------
# hat/shirt character: normalizing an older, differently-shaped source
# ---------------------------------------------------------------------------
def migrate_hatshirt(source_model_path=None, dest_path=None):
    """character_model_hatshirt.json (Part 6/7 output) uses a per-node dict
    keyed by name, each with its own "parent"/"children"/"pivot"/
    "geometry_world"/"is_synthetic_joint" - not the same top-level shape as
    character_lock_walker2.json. This function normalizes it to the SAME
    target schema (components_geometry / pivots_px / hierarchy /
    skeleton / attachments) used for walker2, so both characters expose an
    identical interface to CharacterLockModel.

    Deterministic mapping decisions made here (reported, not silently
    assumed):
      - every node becomes exactly one Bone (rest_pivot = that node's own
        stored "pivot"; rest_orientation_deg = 0.0 for all of them, since
        this character's ENTIRE locked pose was already treated as the
        zero-rotation rest reference in the Part 6/7 work - no baked-in
        rest angle was ever computed or needed for it, unlike walker2).
      - every node with non-empty geometry_world also becomes exactly one
        rigid Attachment bound to its OWN bone (not the nearest ancestor
        joint) - this matches exactly how Part 6/7 already rotated
        subtrees (e.g. rotating "left_arm" moves its geometry-bearing
        descendants because they inherit its world transform through the
        parent chain, not because they share its pivot).
      - a synthetic "root" bone is inserted above "torso_placket" (whose
        own parent was already None) purely for schema-shape consistency
        with walker2 and the requested root->torso->... example; root's
        rest_pivot is set coincident with torso_placket's own pivot,
        since no independent "root" concept existed in the original data.
        This is a structural placeholder, not a semantic claim, and is
        called out explicitly rather than left implicit.
      - all bones use transform_strategy "rigid": this character's
        existing validated rotation test (Part 6/7) never used
        soft_skin_2joint - only single-pivot rigid rotation - so no
        forced two-bone split is introduced where the original data never
        needed one.
    """
    source_model_path = source_model_path or os.path.join(DATA_DIR, "character_model_hatshirt.json")
    dest_path = dest_path or os.path.join(DATA_DIR, "character_lock_hatshirt_v2.json")

    with open(source_model_path) as f:
        nodes = json.load(f)

    components_geometry = {}
    hierarchy = {}
    pivots_px = {}
    skeleton = {"root": {"parent": None, "rest_pivot": None, "rest_orientation_deg": 0.0, "length": None}}
    attachments = {}

    for name, node in nodes.items():
        parent = node["parent"]
        pivots_px[name] = node["pivot"]
        hierarchy[name] = {"parent": parent, "children": node["children"]}
        if node.get("geometry_world"):
            components_geometry[name] = node["geometry_world"]

    root_pivot = list(nodes["torso_placket"]["pivot"])
    skeleton["root"]["rest_pivot"] = root_pivot

    for name, node in nodes.items():
        parent = node["parent"] if node["parent"] is not None else "root"
        parent_pivot = root_pivot if node["parent"] is None else nodes[node["parent"]]["pivot"]
        skeleton[name] = {
            "parent": parent,
            "rest_pivot": list(node["pivot"]),
            "rest_orientation_deg": 0.0,
            "length": _dist(node["pivot"], parent_pivot),
            "transform_strategy": "rigid",
        }
        if node.get("geometry_world"):
            attachments[name] = {"bones": [name], "strategy": "rigid", "geometry": [name], "rigid_children": {}}

    checksum = hashlib.sha256(json.dumps(components_geometry, sort_keys=True).encode()).hexdigest()[:16]

    lock = {
        "character_id": "char_hat_shirt_trousers_v1",
        "locked": True,
        "checksum": checksum,
        "components_geometry": components_geometry,
        "pivots_px": pivots_px,
        "hierarchy": hierarchy,
        "measurements": {"note": "see original character_model_hatshirt.json / Part 1-5 fx/fy landmark table"},
        "ratios": {
            "shoulder_width_over_head_width": {"reference_target": 1.75, "measured_render": 1.79},
            "hip_width_over_shoulder_width": {"design_value": 0.518, "measured_render": 0.51},
            "torso_height_over_leg_height": {"design_value": 0.858, "measured_render": 0.86},
        },
        "skeleton": skeleton,
        "attachments": attachments,
        "heading": {"rest_facing": "right"},
        "views": {"side": {"components_geometry": "components_geometry", "skeleton": "skeleton"}},
    }

    with open(dest_path, "w") as f:
        json.dump(lock, f, indent=1)
    return dest_path


if __name__ == "__main__":
    p1 = migrate_walker2()
    p2 = migrate_hatshirt()
    print("wrote", p1)
    print("wrote", p2)
