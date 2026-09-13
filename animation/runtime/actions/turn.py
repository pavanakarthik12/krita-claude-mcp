"""TurnAction - Phase 2H revision: heading changes smoothly, kept
deliberately separate from bone animation and from the camera (a Pose's
`heading` field is the character's own world orientation; Camera in
camera.py has no idea it exists, and vice versa).

Phase 1's version snapped heading from one value to the other at the turn's
midpoint. This version interpolates it continuously (smoothstep) across
the whole duration - heading is a real, continuously varying scalar in
[-1, 1] (or beyond, for future non-mirrored headings), not a step
function. The renderer (animation/runtime/src/main.cpp) still only has a
single traced silhouette to draw, so it currently uses sign(heading) to
choose a mirrored draw - that is a limitation of the ART (one view, from
POC #4), not of this representation: heading itself is a continuous,
camera-independent orientation value regardless of how few visually
distinct facings the renderer can currently draw.
"""
from .base import Action
from ..pose import Pose


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


class TurnAction(Action):
    affected_bones = ()

    def __init__(self, from_heading: float, to_heading: float):
        self.from_heading = from_heading
        self.to_heading = to_heading

    def evaluate(self, time: float, params: dict, context=None) -> Pose:
        duration = params.get("duration", 0.5)
        progress = _smoothstep(1.0 if duration <= 0 else time / duration)
        pose = Pose()
        pose.heading = self.from_heading + (self.to_heading - self.from_heading) * progress
        return pose
