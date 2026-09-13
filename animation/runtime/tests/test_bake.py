import json
import os
import tempfile

from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.scene import Scene
from animation.runtime.actions import WalkAction, StandAction
from animation.runtime.bake import bake_scene


def _scene():
    asset = CharacterAsset.load()
    scene = Scene(duration=2, fps=24)
    walker = CharacterInstance(asset=asset, world_x=300.0, world_y=650.0, instance_id="walker")
    walker.timeline.add(0, 2, WalkAction())
    stander = CharacterInstance(asset=asset, world_x=800.0, world_y=650.0, instance_id="stander")
    stander.timeline.add(0, 2, StandAction())
    scene.add_character(walker)
    scene.add_character(stander)
    return scene


def test_bake_writes_expected_structure():
    scene = _scene()
    with tempfile.TemporaryDirectory() as d:
        out_path = os.path.join(d, "baked.json")
        baked = bake_scene(scene, out_path)

        assert baked["fps"] == 24
        assert baked["frameCount"] == 48
        assert len(baked["frames"]) == 48
        assert set(baked["characterIds"]) == {"walker", "stander"}

        with open(out_path) as f:
            reloaded = json.load(f)
        assert reloaded == baked


def test_bake_is_deterministic():
    with tempfile.TemporaryDirectory() as d:
        path1 = os.path.join(d, "a.json")
        path2 = os.path.join(d, "b.json")
        baked1 = bake_scene(_scene(), path1)
        baked2 = bake_scene(_scene(), path2)
        assert baked1 == baked2


def test_bake_frame_contains_bone_rotations_and_position():
    scene = _scene()
    with tempfile.TemporaryDirectory() as d:
        baked = bake_scene(scene, os.path.join(d, "baked.json"))
        frame8 = baked["frames"][8]
        assert "thigh_front" in frame8["walker"]["boneRotationDeg"]
        assert frame8["stander"]["boneRotationDeg"] == {}
        assert frame8["walker"]["x"] == 300.0
        assert frame8["stander"]["x"] == 800.0
