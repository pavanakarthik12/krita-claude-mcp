"""WaveAction - an upper-body-only action, designed to be layered as an
overlay (requirement 8): only sets the shoulder/elbow bones of ONE arm, so
Pose.merge can blend it over a base action (e.g. walk) while the legs keep
moving from the base pose."""
import math

from .base import Action
from ..pose import Pose

TWO_PI = 2.0 * math.pi


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


class WaveAction(Action):
    def __init__(self, arm: str = "front"):
        if arm not in ("front", "back"):
            raise ValueError("arm must be 'front' or 'back'")
        self.arm = arm
        self.affected_bones = (f"upper_arm_{arm}", f"forearm_{arm}")

    def evaluate(self, time: float, params: dict, context=None) -> Pose:
        rate = params.get("rate", 2.0)  # waves per second
        amplitude = params.get("amplitude", 20.0)
        raise_deg = params.get("raise_deg", -110.0)  # base arm-up angle
        # Phase 2D fix (found via visual/numeric inspection of the Phase 2
        # test scene: an instant ~110 degree arm snap where the wave
        # overlay began, since as an OVERLAY it isn't covered by the base
        # segment's own transition_in): ease the arm up over `ease`
        # seconds at the start, and back down over the last `ease` seconds
        # of `duration` if a duration is given - self-contained, no change
        # to the generic sequencer/transition mechanism needed.
        ease = params.get("ease", 0.3)
        duration = params.get("duration")

        envelope = 1.0
        if ease > 0:
            envelope = min(envelope, _smoothstep(time / ease))
            if duration is not None:
                envelope = min(envelope, _smoothstep((duration - time) / ease))

        phase = TWO_PI * rate * time
        upper = envelope * (raise_deg + 0.3 * amplitude * math.sin(phase))
        fore = envelope * amplitude * math.sin(phase)

        pose = Pose()
        pose.set_rotation(f"upper_arm_{self.arm}", upper)
        pose.set_rotation(f"forearm_{self.arm}", fore)
        return pose
