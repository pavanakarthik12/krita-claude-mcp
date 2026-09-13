"""CharacterInstance: one independently posed, positioned, animated
character built from a (shared, reusable) CharacterAsset.

Multiple instances from the same asset are completely independent - each
owns its own Sequencer/timeline, world position, heading, and animation
time. Nothing here is shared mutable state between instances (verified in
tests/test_scene.py and, at the DragonBones level, already proven in
POC #4 via factory.buildArmature() per instance).
"""
import itertools
from dataclasses import dataclass, field
from typing import Optional

from .character_asset import CharacterAsset
from .pose import Pose
from .sequencer import Sequencer

_id_counter = itertools.count(1)


@dataclass
class CharacterInstance:
    asset: CharacterAsset
    instance_id: str = field(default=None)
    world_x: float = 0.0
    world_y: float = 0.0
    scale: float = 1.0
    heading: float = 1.0
    timeline: Sequencer = field(default_factory=Sequencer)

    def __post_init__(self):
        if self.instance_id is None:
            self.instance_id = f"char_{next(_id_counter)}"

    def evaluate(self, time: float) -> dict:
        """Returns this instance's full state at `time`: world position,
        heading, and pose. Does not render anything.

        Position = this instance's fixed base position PLUS the timeline's
        cumulative world_delta(time) (Phase 2A locomotion) - character
        LOCAL pose (bone rotations) and WORLD position are kept on two
        entirely separate channels, per requirement."""
        pose: Pose = self.timeline.evaluate(time, context={"asset": self.asset})
        dx, dy = self.timeline.world_delta(time)
        heading = self.timeline.heading_at(time, self.heading)
        return {
            "instance_id": self.instance_id,
            "position": (self.world_x + dx, self.world_y + dy),
            "scale": self.scale,
            "heading": heading,
            "time": time,
            "pose": pose,
        }
