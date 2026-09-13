"""CharacterAsset: the reusable, parsed-once character definition.

Deliberately does NOT re-trace or re-convert the Character Lock. POC #4
already proved the Character Lock -> DragonBones conversion (one shared
armature, four weighted-mesh limbs, six rigid parts); this asset simply
POINTS AT those generated, already-verified files
(animation/dragonbones_poc4/character_ske.json /
parts_manifest.json / parts/*.png) read-only, plus the original Character
Lock JSON for provenance/metadata. Nothing here duplicates that geometry.
"""
import json
import os
from dataclasses import dataclass, field
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_POC4_DIR = os.path.normpath(os.path.join(HERE, "..", "dragonbones_poc4"))
DEFAULT_LOCK_PATH = os.path.normpath(os.path.join(HERE, "..", "data", "character_lock_walker2_v2.json"))

# The only actions this asset's skeleton has been validated against so far
# (POC #4's individual-limb tests + this system's own action set).
AVAILABLE_ACTIONS = ("idle", "walk", "stand", "sit", "wave", "turn")

# bend_sign per leg for the closed-form 2-bone IK fallback (see
# ik2bone.py) - chosen to match each leg's own natural knee direction and
# confirmed by rendering (see the Phase 2 final report).
LEG_BEND_SIGN = {"front": 1.0, "back": -1.0}


def compute_rest_positions(ske_json: dict) -> dict:
    """Every bone's rest GLOBAL position in the armature's own rig
    coordinate system, computed purely from character_ske.json's own
    numbers (no DragonBones runtime involved).

    This relies on a fact established and verified in POC #2/#4: each
    bone's local transform.x/y was deliberately computed as the parent-
    child pivot delta PRE-ROTATED by the negative of the parent's own
    accumulated rest rotation (see convert_character_to_mesh.py's
    build_bones_json / rotate_pt usage). That pre-rotation exists
    specifically so that, combined with DragonBones' own matrix
    composition (child.global = parent.globalMatrix * local_offset), the
    parent's rotation cancels back out - meaning a bone's rest GLOBAL
    position is simply the running SUM of local offsets down the chain,
    with no further rotation needed here. This was verified in POC #2 via
    a direct numerical round-trip against the Character Lock's raw
    rest_pivot values.
    """
    bones = {b["name"]: b for b in ske_json["armature"][0]["bone"]}
    positions = {}

    def resolve(name):
        if name in positions:
            return positions[name]
        b = bones[name]
        t = b["transform"]
        if "parent" not in b:
            positions[name] = (t["x"], t["y"])
        else:
            px, py = resolve(b["parent"])
            positions[name] = (px + t.get("x", 0.0), py + t.get("y", 0.0))
        return positions[name]

    for name in bones:
        resolve(name)
    return positions


def compute_rest_tip(ske_json: dict, bone_name: str) -> Tuple[float, float]:
    """The bone's rest-pose far end ("tip"): its rest global position plus
    its own length along its own rest rotation direction."""
    import math

    bones = {b["name"]: b for b in ske_json["armature"][0]["bone"]}
    positions = compute_rest_positions(ske_json)
    b = bones[bone_name]
    x, y = positions[bone_name]
    length = b.get("length", 0.0)
    rot_deg = b["transform"].get("skX", 0.0)
    rad = math.radians(rot_deg)
    return (x + length * math.cos(rad), y + length * math.sin(rad))


def compute_leg_geometry(ske_json: dict) -> dict:
    """Static per-leg geometry (hip position, bone lengths, rest angle,
    bend direction) the closed-form 2-bone IK solver (ik2bone.py) needs -
    see character_asset.py's LEG_BEND_SIGN and CharacterAsset.load()."""
    import math

    from .ik2bone import LegGeometry

    bones = {b["name"]: b for b in ske_json["armature"][0]["bone"]}
    positions = compute_rest_positions(ske_json)

    legs = {}
    for side, thigh_name, shin_name in (
        ("front", "thigh_front", "shin_front"),
        ("back", "thigh_back", "shin_back"),
    ):
        hip_x, hip_y = positions[thigh_name]
        rest_angle_rad = math.radians(bones[thigh_name]["transform"].get("skX", 0.0))
        legs[side] = LegGeometry(
            hip_x=hip_x,
            hip_y=hip_y,
            upper_length=bones[thigh_name].get("length", 0.0),
            lower_length=bones[shin_name].get("length", 0.0),
            rest_angle_rad=rest_angle_rad,
            bend_sign=LEG_BEND_SIGN[side],
        )
    return legs


@dataclass
class CharacterAsset:
    name: str
    character_lock_path: str
    dragonbones_ske_path: str
    dragonbones_manifest_path: str
    parts_dir: str
    bone_names: Tuple[str, ...] = field(default_factory=tuple)
    mesh_slot_names: Tuple[str, ...] = field(default_factory=tuple)
    rigid_part_names: Tuple[str, ...] = field(default_factory=tuple)
    available_actions: Tuple[str, ...] = AVAILABLE_ACTIONS
    views: Tuple[str, ...] = ("front",)
    # Phase 2B: static per-leg geometry for the closed-form 2-bone IK
    # fallback (see ik2bone.py's module docstring for why it's a fallback
    # rather than DragonBones' own IK constraint), keyed "front"/"back".
    leg_geometry: dict = field(default_factory=dict)

    @staticmethod
    def load(
        name: str = "walker2",
        lock_path: str = DEFAULT_LOCK_PATH,
        poc4_dir: str = DEFAULT_POC4_DIR,
    ) -> "CharacterAsset":
        ske_path = os.path.join(poc4_dir, "character_ske.json")
        manifest_path = os.path.join(poc4_dir, "parts_manifest.json")
        parts_dir = os.path.join(poc4_dir, "parts")

        if not os.path.exists(lock_path):
            raise FileNotFoundError(f"Character Lock not found: {lock_path}")
        if not os.path.exists(ske_path):
            raise FileNotFoundError(
                f"DragonBones asset not found: {ske_path} (run POC #4's "
                f"convert_character_to_mesh.py first - this layer reuses it, "
                f"it does not regenerate it)"
            )

        with open(ske_path) as f:
            ske = json.load(f)
        armature = ske["armature"][0]
        bone_names = tuple(b["name"] for b in armature["bone"])
        mesh_slot_names = tuple(s["name"] for s in armature["skin"][0]["slot"])

        with open(manifest_path) as f:
            manifest = json.load(f)
        rigid_part_names = tuple(p["component"] for p in manifest["parts"])

        leg_geometry = compute_leg_geometry(ske)

        return CharacterAsset(
            name=name,
            character_lock_path=lock_path,
            dragonbones_ske_path=ske_path,
            dragonbones_manifest_path=manifest_path,
            parts_dir=parts_dir,
            bone_names=bone_names,
            mesh_slot_names=mesh_slot_names,
            rigid_part_names=rigid_part_names,
            leg_geometry=leg_geometry,
        )

    def dimensions(self) -> dict:
        """A coarse bounding box in the character's own rest coordinate
        system, derived from the already-generated DragonBones bone list
        (root position) - just enough for a caller to reason about scene
        layout, not a precise silhouette measurement."""
        with open(self.dragonbones_ske_path) as f:
            ske = json.load(f)
        bones = {b["name"]: b for b in ske["armature"][0]["bone"]}
        root = bones["root"]["transform"]
        return {"root_x": root["x"], "root_y": root["y"]}
