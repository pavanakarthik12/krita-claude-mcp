"""SitAction - procedural stand<->sit transition.

standing -> hip lowers -> knees bend -> torso adjusts -> sitting, driven by
a single deterministic progress value in [0, 1] (params["mode"] picks the
direction: "down" for stand->sit, "up" for sit->stand). No IK yet - feet
are not held planted by a solver, they are simply not the focus of this
POC-level action; this is a known, documented simplification (see final
report), not IK "faked" as something it isn't.
"""
from .base import Action
from ..pose import BoneChannel, Pose


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


class SitAction(Action):
    affected_bones = (
        "root", "torso",
        "thigh_front", "shin_front", "thigh_back", "shin_back",
    )

    def evaluate(self, time: float, params: dict) -> Pose:
        duration = params.get("duration", 1.0)
        mode = params.get("mode", "down")  # "down": stand->sit, "up": sit->stand

        raw_progress = _smoothstep(time / duration) if duration > 0 else 1.0
        progress = raw_progress if mode == "down" else 1.0 - raw_progress

        hip_drop = 90.0 * progress
        thigh_bend = 75.0 * progress
        shin_bend = 100.0 * progress
        torso_lean = -8.0 * progress

        pose = Pose()
        pose.bones["root"] = BoneChannel(rotation_deg=0.0, translation=(0.0, hip_drop))
        pose.set_rotation("torso", torso_lean)
        pose.set_rotation("thigh_front", thigh_bend)
        pose.set_rotation("shin_front", -shin_bend)
        pose.set_rotation("thigh_back", thigh_bend)
        pose.set_rotation("shin_back", -shin_bend)
        return pose
