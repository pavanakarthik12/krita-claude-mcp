"""Builds the section-17 test scene (10s/24fps, 3 characters, all sharing
one CharacterAsset) and bakes it to test_output/baked_scene.json for the
C++ DragonBones adapter to consume and render.

Run from animation/runtime/:
    py -3 build_test_scene.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.scene import Scene
from animation.runtime.camera import Camera
from animation.runtime.actions import IdleAction, WalkAction, StandAction, SitAction, WaveAction
from animation.runtime.bake import bake_scene

HERE = os.path.dirname(os.path.abspath(__file__))


def build_scene() -> Scene:
    asset = CharacterAsset.load()

    # Same camera framing POC #4 needed: the character's own rest
    # proportions (head-to-foot) are taller than a 1:1 700px canvas, so the
    # camera is zoomed out around a world center high enough to fit heads
    # and low enough to fit feet - this is exactly what POC #4's view-rect
    # fix established, now expressed through Camera instead of being
    # hardcoded in the renderer.
    camera = Camera(x=1157.0, y=650.0, zoom=700.0 / 1350.0, viewport_width=1200, viewport_height=700)

    scene = Scene(duration=10.0, fps=24, camera=camera)

    # Character 1: 0-2 idle, 2-5 walk, 5-6 stop, 6-8 wave (overlay on stand),
    # 8-10 walk.
    char1 = CharacterInstance(asset=asset, world_x=675.0, world_y=650.0, instance_id="char1")
    char1.timeline.add(0.0, 2.0, IdleAction())
    char1.timeline.add(2.0, 5.0, WalkAction())
    char1.timeline.add(5.0, 6.0, StandAction())
    char1.timeline.add(6.0, 8.0, StandAction())
    char1.timeline.add_overlay(6.0, 8.0, WaveAction(arm="front"), {"rate": 2.0, "amplitude": 20.0})
    char1.timeline.add(8.0, 10.0, WalkAction())

    # Character 2: 0-3 stand, 3-5 sit (transition down), 5-7 sit (held),
    # 7-9 stand (transition up), 9-10 stand (held).
    char2 = CharacterInstance(asset=asset, world_x=1639.0, world_y=650.0, instance_id="char2")
    char2.timeline.add(0.0, 3.0, StandAction())
    char2.timeline.add(3.0, 5.0, SitAction(), {"duration": 2.0, "mode": "down"})
    char2.timeline.add(5.0, 7.0, SitAction(), {"duration": 0.01, "mode": "down"})
    char2.timeline.add(7.0, 9.0, SitAction(), {"duration": 2.0, "mode": "up"})
    char2.timeline.add(9.0, 10.0, StandAction())

    # Character 3: static for the entire scene - the reusability proof
    # (same asset, third independent instance, no animation at all).
    char3 = CharacterInstance(asset=asset, world_x=1157.0, world_y=650.0, instance_id="char3")
    char3.timeline.add(0.0, 10.0, StandAction())

    scene.add_character(char1)
    scene.add_character(char2)
    scene.add_character(char3)
    return scene


def main():
    scene = build_scene()
    out_dir = os.path.join(HERE, "test_output")
    os.makedirs(out_dir, exist_ok=True)
    baked_path = os.path.join(out_dir, "baked_scene.json")
    baked = bake_scene(scene, baked_path)
    print(f"Baked {baked['frameCount']} frames for characters {baked['characterIds']} -> {baked_path}")


if __name__ == "__main__":
    main()
