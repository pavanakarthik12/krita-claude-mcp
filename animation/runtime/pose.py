"""
Pose: a pure data description of a character's instantaneous skeletal state.

A Pose never touches DragonBones, SFML, or Krita - it is the hand-off point
between our high-level animation intelligence (Action/Sequencer/Scene) and
the low-level DragonBones adapter, which is the only place bone transforms
are actually *applied* to a real armature.

Bone names used here are the Character Lock's own bone names (also used
verbatim as the DragonBones armature's bone names, per POC #4).
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class BoneChannel:
    rotation_deg: float = 0.0
    translation: Tuple[float, float] = (0.0, 0.0)


@dataclass
class IKTarget:
    x: float
    y: float
    enabled: bool = True


@dataclass
class Pose:
    bones: Dict[str, BoneChannel] = field(default_factory=dict)
    ik: Dict[str, IKTarget] = field(default_factory=dict)
    # None means "this pose does not opine on heading" - the instance keeps
    # whatever heading it already had. Only turn-like actions set this.
    heading: Optional[float] = None

    @staticmethod
    def identity() -> "Pose":
        return Pose()

    def set_rotation(self, bone_name: str, degrees: float) -> None:
        self.bones[bone_name] = BoneChannel(rotation_deg=degrees)

    def get_rotation(self, bone_name: str) -> float:
        chan = self.bones.get(bone_name)
        return chan.rotation_deg if chan is not None else 0.0

    def bone_rotation_map(self) -> Dict[str, float]:
        """Flat {bone_name: degrees} - what the DragonBones adapter actually
        consumes (translation/IK are not yet wired into the C++ adapter,
        see the final report's "what's next")."""
        return {name: chan.rotation_deg for name, chan in self.bones.items()}

    @staticmethod
    def merge(base: "Pose", overlay: "Pose", bone_mask: Tuple[str, ...]) -> "Pose":
        """Returns a new Pose: base's bones everywhere, except the bones in
        bone_mask which - if the overlay actually sets them - come from the
        overlay instead. This is the entire "blending" system (requirement
        11): a deliberately simple, deterministic, semantic-level operation,
        not a re-implementation of DragonBones' own blending math."""
        merged = Pose(bones=dict(base.bones), ik=dict(base.ik))
        for name in bone_mask:
            if name in overlay.bones:
                merged.bones[name] = overlay.bones[name]
        for name, target in overlay.ik.items():
            if name in bone_mask or not bone_mask:
                merged.ik[name] = target
        # An overlay is upper-/lower-body layering, not a heading change -
        # heading intentionally does not propagate from an overlay.
        return merged
