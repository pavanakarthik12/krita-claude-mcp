"""Action: semantic motion abstraction. An Action knows nothing about
Krita, DragonBones, or rendering - it is a pure function of (time,
parameters) -> Pose. Deterministic: the same (time, parameters) must always
produce the same Pose (see tests/test_determinism.py)."""
from abc import ABC, abstractmethod

from ..pose import Pose


class Action(ABC):
    #: bone names this action is allowed to touch, used by the sequencer to
    #: mask overlay blending (Pose.merge). Empty tuple = "no restriction,
    #: touches whatever it wants" (used by base/full-body actions).
    affected_bones: tuple = ()

    @abstractmethod
    def evaluate(self, time: float, params: dict) -> Pose:
        """time is seconds elapsed since this action segment started (i.e.
        already local to the action, not the scene's global clock) -
        Walk.evaluate(0.137) and Walk.evaluate(1.842) must both work with no
        prior state, per requirement 6."""
        raise NotImplementedError
