"""Camera: a minimal, static description of how the scene is framed.
Deliberately independent of any character transform (requirement 13/19's
"camera is independent from character transforms" check) and not
implemented with any movement yet - just position/zoom/rotation/viewport.
"""
from dataclasses import dataclass


@dataclass
class Camera:
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0
    rotation: float = 0.0
    viewport_width: int = 1200
    viewport_height: int = 700
