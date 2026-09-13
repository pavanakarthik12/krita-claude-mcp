"""WaveAction - an upper-body-only action, designed to be layered as an
overlay (requirement 8): only sets the shoulder/elbow bones of ONE arm, so
Pose.merge can blend it over a base action (e.g. walk) while the legs keep
moving from the base pose."""
import math

from .base import Action
from ..pose import Pose

TWO_PI = 2.0 * math.pi


class WaveAction(Action):
    def __init__(self, arm: str = "front"):
        if arm not in ("front", "back"):
            raise ValueError("arm must be 'front' or 'back'")
        self.arm = arm
        self.affected_bones = (f"upper_arm_{arm}", f"forearm_{arm}")

    def evaluate(self, time: float, params: dict) -> Pose:
        rate = params.get("rate", 2.0)  # waves per second
        amplitude = params.get("amplitude", 20.0)
        raise_deg = params.get("raise_deg", -110.0)  # base arm-up angle

        phase = TWO_PI * rate * time
        upper = raise_deg + 0.3 * amplitude * math.sin(phase)
        fore = amplitude * math.sin(phase)

        pose = Pose()
        pose.set_rotation(f"upper_arm_{self.arm}", upper)
        pose.set_rotation(f"forearm_{self.arm}", fore)
        return pose
