"""IdleAction - a small, deterministic breathing sway. Distinct from
StandAction (dead rest pose) so a sequencer transition idle -> walk has
somewhere to visibly start from."""
import math

from .base import Action
from ..pose import Pose

TWO_PI = 2.0 * math.pi


class IdleAction(Action):
    affected_bones = ("torso", "head")

    def evaluate(self, time: float, params: dict, context=None) -> Pose:
        breath_hz = params.get("breath_rate", 0.25)
        amplitude = params.get("amplitude", 1.5)
        phase = TWO_PI * breath_hz * time
        pose = Pose()
        pose.set_rotation("torso", amplitude * math.sin(phase))
        pose.set_rotation("head", -0.5 * amplitude * math.sin(phase))
        return pose
