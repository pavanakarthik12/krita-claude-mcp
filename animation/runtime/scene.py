"""Scene: the top-level container - characters, camera, duration, fps.
scene.evaluate(time) is the one central deterministic evaluator: it returns
every character's state at that instant and performs NO rendering.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from .camera import Camera
from .character_instance import CharacterInstance


@dataclass
class Scene:
    duration: float
    fps: int = 24
    camera: Camera = field(default_factory=Camera)
    characters: List[CharacterInstance] = field(default_factory=list)

    def add_character(self, character: CharacterInstance) -> "Scene":
        self.characters.append(character)
        return self

    def evaluate(self, time: float) -> Dict[str, dict]:
        return {c.instance_id: c.evaluate(time) for c in self.characters}

    def frame_count(self) -> int:
        return int(round(self.duration * self.fps))

    def frame_times(self):
        for frame in range(self.frame_count()):
            yield frame, frame / float(self.fps)
