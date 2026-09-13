"""TurnAction - changes heading (left/right facing), kept deliberately
separate from bone animation and from the camera (requirement 9). This POC
implements a deterministic snap (heading flips at the midpoint of the
turn's duration) rather than a smooth in-place spin animation - turning a
2D side-view character smoothly would need its own silhouette work that is
out of scope here; the important, testable property is that heading is a
pure function of time and is never confused with camera facing."""
from .base import Action
from ..pose import Pose


class TurnAction(Action):
    affected_bones = ()

    def __init__(self, from_heading: float, to_heading: float):
        self.from_heading = from_heading
        self.to_heading = to_heading

    def evaluate(self, time: float, params: dict) -> Pose:
        duration = params.get("duration", 0.5)
        progress = 0.0 if duration <= 0 else min(1.0, time / duration)
        pose = Pose()
        pose.heading = self.from_heading if progress < 0.5 else self.to_heading
        return pose
