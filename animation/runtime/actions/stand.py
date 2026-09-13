"""StandAction - the dead rest pose (all bone deltas zero). Also the
implicit target SitAction interpolates away from on stand->sit and the
pose sit->stand ends at (see SitAction for the shared progress logic)."""
from .base import Action
from ..pose import Pose


class StandAction(Action):
    affected_bones = ()  # touches every bone (returns to rest everywhere)

    def evaluate(self, time: float, params: dict, context=None) -> Pose:
        return Pose.identity()
