"""WalkAction - coordinated four-limb walk cycle.

The per-bone formula is the same mechanically-coordinated pattern proven in
POC #2/#4 (opposite-phase thighs, one-directional knee/elbow lag, hip
bounce, torso/head stabilization) generalized to:
  - evaluate at any arbitrary time (no fixed frame count)
  - parameterized speed/stride/bounce/direction

DragonBones itself does the actual skinning/rendering; this only produces a
Pose (bone-name -> rotation degrees + a root translation for hip bounce).
"""
import math

from .base import Action
from ..pose import BoneChannel, Pose

TWO_PI = 2.0 * math.pi


class WalkAction(Action):
    affected_bones = (
        "root", "torso", "head",
        "thigh_front", "shin_front", "thigh_back", "shin_back",
        "upper_arm_front", "forearm_front", "upper_arm_back", "forearm_back",
    )

    def evaluate(self, time: float, params: dict) -> Pose:
        speed = params.get("speed", 1.0)      # gait cycles per second
        stride = params.get("stride", 1.0)    # thigh/shin swing amplitude multiplier
        bounce = params.get("bounce", 1.0)    # hip bounce amplitude multiplier
        direction = params.get("direction", 1.0)  # +1 forward, -1 backward gait

        phase = TWO_PI * speed * time * direction

        thigh_f = stride * 30.0 * math.sin(phase)
        thigh_b = stride * 30.0 * math.sin(phase + math.pi)
        shin_f = stride * 22.0 * max(0.0, math.sin(phase + math.pi / 2.0))
        shin_b = stride * 22.0 * max(0.0, math.sin(phase + math.pi + math.pi / 2.0))

        upper_arm_f = stride * 26.0 * math.sin(phase + math.pi)
        upper_arm_b = stride * 26.0 * math.sin(phase)
        forearm_f = stride * 14.0 * max(0.0, math.sin(phase + math.pi + math.pi / 2.0))
        forearm_b = stride * 14.0 * max(0.0, math.sin(phase + math.pi / 2.0))

        hip_bounce = -bounce * 6.0 * abs(math.sin(phase))
        torso_stabilize = -stride * 3.0 * math.sin(phase)
        head_stabilize = stride * 1.5 * math.sin(phase)

        pose = Pose()
        pose.set_rotation("thigh_front", thigh_f)
        pose.set_rotation("shin_front", shin_f)
        pose.set_rotation("thigh_back", thigh_b)
        pose.set_rotation("shin_back", shin_b)
        pose.set_rotation("upper_arm_front", upper_arm_f)
        pose.set_rotation("forearm_front", forearm_f)
        pose.set_rotation("upper_arm_back", upper_arm_b)
        pose.set_rotation("forearm_back", forearm_b)
        pose.set_rotation("torso", torso_stabilize)
        pose.set_rotation("head", head_stabilize)
        pose.bones["root"] = BoneChannel(rotation_deg=0.0, translation=(0.0, hip_bounce))
        return pose
