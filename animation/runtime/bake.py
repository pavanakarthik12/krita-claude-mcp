"""bake.py: serializes a Scene's per-frame evaluation into a plain JSON file
the C++ DragonBones adapter (animation/runtime/src/main.cpp) consumes.

This is the hand-off point between "our deterministic animation
intelligence" (pure Python, unit-tested with no DragonBones/SFML
dependency at all) and "the DragonBones adapter" (C++, applies the already-
decided Pose to a real armature and renders it) - the intelligence layer
never touches bone-transform or skinning math itself.
"""
import json

from .scene import Scene


def bake_scene(scene: Scene, out_path: str) -> dict:
    baked = {
        "fps": scene.fps,
        "frameCount": scene.frame_count(),
        "width": scene.camera.viewport_width,
        "height": scene.camera.viewport_height,
        "camera": {
            "x": scene.camera.x,
            "y": scene.camera.y,
            "zoom": scene.camera.zoom,
            "rotation": scene.camera.rotation,
        },
        "characterIds": [c.instance_id for c in scene.characters],
        "frames": [],
    }

    for frame, t in scene.frame_times():
        frame_state = {}
        for char_id, state in scene.evaluate(t).items():
            pose = state["pose"]
            translations = {
                name: list(chan.translation)
                for name, chan in pose.bones.items()
                if chan.translation != (0.0, 0.0)
            }
            frame_state[char_id] = {
                "boneRotationDeg": pose.bone_rotation_map(),
                "translations": translations,
                "x": state["position"][0],
                "y": state["position"][1],
                "heading": state["heading"],
            }
        baked["frames"].append(frame_state)

    with open(out_path, "w") as f:
        json.dump(baked, f)

    return baked
