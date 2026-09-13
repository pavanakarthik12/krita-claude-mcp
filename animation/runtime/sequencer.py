"""AnimationSequencer: orders Actions on a timeline and evaluates the
correct one (plus any active overlays) at an arbitrary time. Deterministic:
the same (segments, time) always yields the same Pose - no hidden state,
no dependence on having been evaluated in order.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .actions.base import Action
from .pose import Pose


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


@dataclass
class Segment:
    start: float
    end: float
    action: Action
    params: dict = field(default_factory=dict)
    #: Phase 2D: seconds, from `start`, spent cross-fading in from the
    #: PREVIOUS segment's final pose instead of jumping straight to this
    #: action's own t=0 pose - see Sequencer.evaluate. 0 = no transition
    #: (Phase 1 behavior, unchanged).
    transition_in: float = 0.0

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end


class Sequencer:
    def __init__(self):
        self._segments: List[Segment] = []
        self._overlays: List[Segment] = []

    def add(
        self,
        start: float,
        end: float,
        action: Action,
        params: Optional[dict] = None,
        transition_in: float = 0.0,
    ) -> "Sequencer":
        if end <= start:
            raise ValueError(f"segment end ({end}) must be after start ({start})")
        self._segments.append(Segment(start, end, action, params or {}, transition_in))
        self._segments.sort(key=lambda s: s.start)
        return self

    def add_overlay(self, start: float, end: float, action: Action, params: Optional[dict] = None) -> "Sequencer":
        if end <= start:
            raise ValueError(f"overlay end ({end}) must be after start ({start})")
        self._overlays.append(Segment(start, end, action, params or {}))
        return self

    def _active_base_segment(self, t: float) -> Optional[Segment]:
        for seg in self._segments:
            if seg.contains(t):
                return seg
        if not self._segments:
            return None
        # Outside every segment: hold the nearest boundary segment's edge
        # pose rather than returning nothing - keeps evaluate() total.
        if t < self._segments[0].start:
            return self._segments[0]
        return self._segments[-1]

    def duration(self) -> float:
        if not self._segments:
            return 0.0
        return max(seg.end for seg in self._segments)

    def evaluate(self, t: float, context: Optional[dict] = None) -> Pose:
        base_seg = self._active_base_segment(t)
        if base_seg is None:
            return Pose.identity()

        local_t = min(max(t, base_seg.start), base_seg.end) - base_seg.start
        pose = base_seg.action.evaluate(local_t, base_seg.params, context)

        # Phase 2D: generic transition blending - cross-fade in from
        # whatever pose the PREVIOUS segment ended on, instead of jumping
        # straight to this action's own t=0 pose. Works for any pair of
        # actions with no special-casing: it is just Pose.lerp between two
        # already-computed poses.
        if base_seg.transition_in > 0 and t < base_seg.start + base_seg.transition_in:
            prev_seg = None
            for seg in self._segments:
                if seg is base_seg:
                    break
                prev_seg = seg
            if prev_seg is not None:
                prev_local_t = prev_seg.end - prev_seg.start
                prev_pose = prev_seg.action.evaluate(prev_local_t, prev_seg.params, context)
                # Bug found via Phase 2 visual inspection: freezing only
                # the previous BASE action's pose ignored any overlay that
                # was actually visible right up to the hand-off (e.g. a
                # wave overlaid on "stand" until t=8, followed by a
                # transition into "walk" at t=8) - the frozen frame must
                # include whatever overlay was active at that instant too,
                # or the transition blends away the overlay's own effect
                # in a single frame (a real pop, not a smooth fade-out).
                for ov in self._overlays:
                    if ov.start <= prev_seg.end <= ov.end:
                        ov_local_t = prev_seg.end - ov.start
                        overlay_pose = ov.action.evaluate(ov_local_t, ov.params, context)
                        prev_pose = Pose.merge(prev_pose, overlay_pose, ov.action.affected_bones)
                alpha = _smoothstep((t - base_seg.start) / base_seg.transition_in)
                pose = Pose.lerp(prev_pose, pose, alpha)

        for ov in self._overlays:
            if ov.contains(t):
                ov_local_t = t - ov.start
                overlay_pose = ov.action.evaluate(ov_local_t, ov.params, context)
                pose = Pose.merge(pose, overlay_pose, ov.action.affected_bones)

        return pose

    def heading_at(self, t: float, default_heading: float) -> float:
        """Phase 2H fix: TurnAction only opines on heading during its own
        segment (Pose.heading is None everywhere else) - heading must be
        STICKY (the character's world orientation persists after the turn
        finishes), not reset the instant the turn segment ends. This scans
        every base segment up to `t` and keeps the LAST non-None heading
        any of them reported, falling back to `default_heading` if no
        segment ever set one. (Cheap at this POC's timeline sizes; a real
        system would cache this instead of re-evaluating past segments.)
        """
        result = default_heading
        for seg in self._segments:
            if seg.start > t:
                break
            local_t = min(t, seg.end) - seg.start
            pose = seg.action.evaluate(local_t, seg.params)
            if pose.heading is not None:
                result = pose.heading
        return result

    def world_delta(self, t: float, params: Optional[dict] = None) -> Tuple[float, float]:
        """Phase 2A: cumulative world-space displacement at time t, summed
        from every base segment's own world_delta up to t - a pure
        function of t and the (static) segment list, so repeated calls at
        the same t always agree (requirement: 'the position at time t must
        be deterministic')."""
        total_x, total_y = 0.0, 0.0
        for seg in self._segments:
            if t <= seg.start:
                continue
            local_t = min(t, seg.end) - seg.start
            if local_t <= 0:
                continue
            dx, dy = seg.action.world_delta(local_t, seg.params)
            total_x += dx
            total_y += dy
        return (total_x, total_y)
