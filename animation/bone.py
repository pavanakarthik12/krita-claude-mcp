"""
Generic Bone data structure for arbitrary-depth skeletons.

A Bone never contains geometry. It only describes where a joint sits at
rest and how it's connected to its parent - the same kind of data
walker2_build_lock.py / walker2_animate_articulated.py already computed
ad hoc (pivots_px, rest angles derived via atan2) and passed around as loose
variables. This module just gives that data a name and a stable shape.

transform_strategy is a property of a bone (or more precisely, of the
attachment that uses it - see character_model.py) rather than a global
assumption: "rigid" bones move as an undeformed unit (transform_rigid /
transform_distal_rigid in articulation_lib.py); "soft_skin_2joint" bones
are the two-bone case where a single traced contour is smoothly bent
between a parent and child bone (transform_two_joint in articulation_lib.py).
Nothing here reimplements that math - see transform_evaluator.py for the
dispatch.
"""
from dataclasses import dataclass, field
from typing import Optional, Literal

TransformStrategy = Literal["rigid", "soft_skin_2joint"]


@dataclass(frozen=True)
class Bone:
    name: str
    parent: Optional[str]              # bone name, or None for a root bone
    rest_pivot: tuple                  # (x, y) in the character's rest/local space
    rest_orientation_deg: float = 0.0  # this bone's own inherent rest angle,
                                        # relative to its parent's rest orientation
                                        # (0.0 for rigid, non-articulated bones)
    length: Optional[float] = None     # distance from parent.rest_pivot to this
                                        # bone's rest_pivot; None only for a root
                                        # bone, which has no parent to measure from
    transform_strategy: TransformStrategy = "rigid"

    def to_dict(self):
        d = {
            "parent": self.parent,
            "rest_pivot": list(self.rest_pivot),
            "rest_orientation_deg": self.rest_orientation_deg,
            "length": self.length,
        }
        if self.parent is not None:
            d["transform_strategy"] = self.transform_strategy
        return d

    @staticmethod
    def from_dict(name, d):
        return Bone(
            name=name,
            parent=d.get("parent"),
            rest_pivot=tuple(d["rest_pivot"]),
            rest_orientation_deg=float(d.get("rest_orientation_deg", 0.0)),
            length=d.get("length"),
            transform_strategy=d.get("transform_strategy", "rigid"),
        )


@dataclass(frozen=True)
class Attachment:
    """Binds one or more geometry components (components_geometry keys) to
    one or two bones. Two bones only for strategy="soft_skin_2joint" (the
    proximal bone supplies theta1, the distal bone's own rotation supplies
    theta2 for the weighted blend - see transform_evaluator.py). rigid_children
    names components that ride rigidly at the attachment's distal bone
    (e.g. a hand at the end of a forearm) without being part of the blended
    contour themselves."""
    name: str
    bones: tuple                       # 1 bone for "rigid", 2 for "soft_skin_2joint"
    strategy: TransformStrategy
    geometry: tuple                    # components_geometry keys this attachment moves
    rigid_children: dict = field(default_factory=dict)  # {geometry_key: bone_name}

    def to_dict(self):
        return {
            "bones": list(self.bones),
            "strategy": self.strategy,
            "geometry": list(self.geometry),
            "rigid_children": dict(self.rigid_children),
        }

    @staticmethod
    def from_dict(name, d):
        return Attachment(
            name=name,
            bones=tuple(d["bones"]),
            strategy=d["strategy"],
            geometry=tuple(d["geometry"]),
            rigid_children=dict(d.get("rigid_children", {})),
        )
