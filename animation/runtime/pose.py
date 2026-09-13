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
    def lerp(a: "Pose", b: "Pose", alpha: float) -> "Pose":
        """Full bone-by-bone linear interpolation between two poses over
        the UNION of bones each one touches (a bone only one side mentions
        is treated as 0 rotation/translation on the other side) - this is
        the generic mechanism Phase 2D's transition blending uses to avoid
        popping at an action-to-action seam, deliberately distinct from
        Pose.merge (a masked override, used for overlays like wave)."""
        alpha = max(0.0, min(1.0, alpha))
        result = Pose()
        for name in set(a.bones) | set(b.bones):
            ca = a.bones.get(name, BoneChannel())
            cb = b.bones.get(name, BoneChannel())
            rot = ca.rotation_deg + (cb.rotation_deg - ca.rotation_deg) * alpha
            tx = ca.translation[0] + (cb.translation[0] - ca.translation[0]) * alpha
            ty = ca.translation[1] + (cb.translation[1] - ca.translation[1]) * alpha
            result.bones[name] = BoneChannel(rotation_deg=rot, translation=(tx, ty))

        if a.heading is not None and b.heading is not None:
            result.heading = a.heading + (b.heading - a.heading) * alpha
        elif b.heading is not None:
            result.heading = b.heading
        else:
            result.heading = a.heading

        result.ik = dict(b.ik) if alpha >= 0.5 else dict(a.ik)
        return result

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
