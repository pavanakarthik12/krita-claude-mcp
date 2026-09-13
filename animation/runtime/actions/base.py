"""Action: semantic motion abstraction. An Action knows nothing about
Krita, DragonBones, or rendering - it is a pure function of (time,
parameters[, context]) -> Pose. Deterministic: the same inputs must always
produce the same Pose (see tests/test_determinism.py)."""
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from ..pose import Pose


class Action(ABC):
    #: bone names this action is allowed to touch, used by the sequencer to
    #: mask overlay blending (Pose.merge). Empty tuple = "no restriction,
    #: touches whatever it wants" (used by base/full-body actions).
    affected_bones: tuple = ()

    @abstractmethod
    def evaluate(self, time: float, params: dict, context: Optional[dict] = None) -> Pose:
        """time is seconds elapsed since this action segment started (i.e.
        already local to the action, not the scene's global clock) -
        Walk.evaluate(0.137) and Walk.evaluate(1.842) must both work with no
        prior state, per requirement 6.

        `context` is optional, read-only, instance-supplied data an action
        MAY use (currently just {"asset": CharacterAsset} - see WalkAction's
        use of asset.leg_geometry for foot-contact IK). It is never required:
        every action must still produce a sensible pose with context=None,
        which is exactly how the Phase 1 unit tests call these directly.
        """
        raise NotImplementedError

    def world_delta(self, time: float, params: dict) -> Tuple[float, float]:
        """Phase 2A locomotion: how far THIS action has moved the character
        in world space after `time` seconds of its own local clock, as a
        pure function of time (never accumulated/stateful) - see
        Sequencer.world_delta for how per-segment deltas are summed into an
        instance's total position. Bone geometry itself is never used to
        carry movement (requirement: "do NOT bake movement into the
        character's bone geometry" - world_delta is a separate channel from
        Pose entirely). Default: this action does not move the character."""
        return (0.0, 0.0)
