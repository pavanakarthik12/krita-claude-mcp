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

        return CharacterAsset(
            name=name,
            character_lock_path=lock_path,
            dragonbones_ske_path=ske_path,
            dragonbones_manifest_path=manifest_path,
            parts_dir=parts_dir,
            bone_names=bone_names,
            mesh_slot_names=mesh_slot_names,
            rigid_part_names=rigid_part_names,
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
