"""Phase 2I: the motion-quality test scene - 15s/24fps, 3 characters,
exercising locomotion, foot-contact IK, generic transition blending,
overlay (wave-while-standing... and this scene also proves wave layered
mid-timeline), deceleration, and heading, all from the SAME CharacterAsset.

Run from animation/runtime/:
    py -3 build_test_scene_phase2.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.scene import Scene
from animation.runtime.camera import Camera
from animation.runtime.actions import (
    IdleAction, WalkAction, StandAction, SitAction, WaveAction, TurnAction, StopAction,
)
from animation.runtime.bake import bake_scene

HERE = os.path.dirname(os.path.abspath(__file__))
WALK_SPEED = 55.0
GAIT_HZ = 1.0


def build_scene() -> Scene:
    asset = CharacterAsset.load()

    camera = Camera(x=1157.0, y=650.0, zoom=700.0 / 1350.0, viewport_width=1200, viewport_height=700)
    scene = Scene(duration=15.0, fps=24, camera=camera)

    # --- Character 1 ---
    # 0-2 idle | 2-5 walk right | 5-6 decelerate+stop | 6-8 wave | 8-10 walk
    # right | 10-11.5 stop | 11.5-13 sit | 13-15 stand
    char1 = CharacterInstance(asset=asset, world_x=675.0, world_y=650.0, instance_id="char1")
    walk_params = {"speed": WALK_SPEED, "gait_hz": GAIT_HZ, "direction": 1.0}

    char1.timeline.add(0.0, 2.0, IdleAction())
    char1.timeline.add(2.0, 5.0, WalkAction(), walk_params, transition_in=0.4)
    char1.timeline.add(5.0, 6.0, StopAction(), {
        "duration": 1.0, "initial_speed": WALK_SPEED, "gait_hz": GAIT_HZ,
        "initial_stride": 1.0, "initial_bounce": 1.0, "direction": 1.0,
    })
    char1.timeline.add(6.0, 8.0, StandAction())
    char1.timeline.add_overlay(6.0, 8.0, WaveAction(arm="front"), {"rate": 2.0, "amplitude": 20.0, "duration": 2.0, "ease": 0.3})
    char1.timeline.add(8.0, 10.0, WalkAction(), walk_params, transition_in=0.4)
    char1.timeline.add(10.0, 11.5, StopAction(), {
        "duration": 1.5, "initial_speed": WALK_SPEED, "gait_hz": GAIT_HZ,
        "initial_stride": 1.0, "initial_bounce": 1.0, "direction": 1.0,
    })
    char1.timeline.add(11.5, 13.0, SitAction(), {"duration": 1.5, "mode": "down"}, transition_in=0.3)
    char1.timeline.add(13.0, 15.0, SitAction(), {"duration": 1.5, "mode": "up"}, transition_in=0.0)

    # --- Character 2 ---
    # 0-4 stand | 4-6 sit (down) | 6-8 sit (held) | 8-10 stand (up) |
    # 10-15 walk left (heading turns to face travel just beforehand)
    char2 = CharacterInstance(asset=asset, world_x=1639.0, world_y=650.0, instance_id="char2", heading=1.0)
    char2.timeline.add(0.0, 4.0, StandAction())
    char2.timeline.add(4.0, 6.0, SitAction(), {"duration": 2.0, "mode": "down"}, transition_in=0.3)
    char2.timeline.add(6.0, 8.0, SitAction(), {"duration": 0.01, "mode": "down"})
    char2.timeline.add(8.0, 9.7, SitAction(), {"duration": 1.7, "mode": "up"}, transition_in=0.3)
    char2.timeline.add(9.7, 10.0, TurnAction(from_heading=1.0, to_heading=-1.0), {"duration": 0.3})
    char2.timeline.add(10.0, 15.0, WalkAction(), {"speed": WALK_SPEED, "gait_hz": GAIT_HZ, "direction": -1.0}, transition_in=0.4)

    # --- Character 3: static for the entire scene ---
    char3 = CharacterInstance(asset=asset, world_x=1157.0, world_y=650.0, instance_id="char3")
    char3.timeline.add(0.0, 15.0, StandAction())

    scene.add_character(char1)
    scene.add_character(char2)
    scene.add_character(char3)
    return scene


def main():
    scene = build_scene()
    out_dir = os.path.join(HERE, "test_output_phase2")
    os.makedirs(out_dir, exist_ok=True)
    baked_path = os.path.join(out_dir, "baked_scene.json")
    baked = bake_scene(scene, baked_path)
    print(f"Baked {baked['frameCount']} frames for characters {baked['characterIds']} -> {baked_path}")


if __name__ == "__main__":
    main()
