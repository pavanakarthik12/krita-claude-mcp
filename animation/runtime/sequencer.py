"""AnimationSequencer: orders Actions on a timeline and evaluates the
correct one (plus any active overlays) at an arbitrary time. Deterministic:
the same (segments, time) always yields the same Pose - no hidden state,
no dependence on having been evaluated in order.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .actions.base import Action
from .pose import Pose


@dataclass
class Segment:
    start: float
    end: float
    action: Action
    params: dict = field(default_factory=dict)

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end


class Sequencer:
    def __init__(self):
        self._segments: List[Segment] = []
        self._overlays: List[Segment] = []

    def add(self, start: float, end: float, action: Action, params: Optional[dict] = None) -> "Sequencer":
        if end <= start:
            raise ValueError(f"segment end ({end}) must be after start ({start})")
        self._segments.append(Segment(start, end, action, params or {}))
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

    def evaluate(self, t: float) -> Pose:
        base_seg = self._active_base_segment(t)
        if base_seg is None:
            return Pose.identity()

        local_t = min(max(t, base_seg.start), base_seg.end) - base_seg.start
        pose = base_seg.action.evaluate(local_t, base_seg.params)

        for ov in self._overlays:
            if ov.contains(t):
                ov_local_t = t - ov.start
                overlay_pose = ov.action.evaluate(ov_local_t, ov.params)
                pose = Pose.merge(pose, overlay_pose, ov.action.affected_bones)

        return pose
