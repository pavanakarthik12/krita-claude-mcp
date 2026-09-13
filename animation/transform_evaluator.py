"""
Generic top-down forward-kinematics evaluator for an arbitrary-depth
Bone hierarchy.

world_transform(bone, pose):
    if bone.parent is None:
        rest(bone) . pose_delta(bone)
    else:
        world_transform(bone.parent, pose) . rest_relative(bone) . pose_delta(bone)

This module contains NO new transform math. It composes rotations/
translations generically (bone_world_pivot / bone_world_rotation below),
then for GEOMETRY it dispatches to the existing, already-integrity-tested
functions in articulation_lib.py:
    - "rigid"           -> transform_rigid / transform_distal_rigid
    - "soft_skin_2joint" -> transform_two_joint (unchanged, imported as-is)

At an all-zero Pose, every dispatch reduces to a bone's own rest_pivot with
zero rotation, which is exactly the locked geometry unchanged - this is
what test_transform_evaluator.py's zero-pose regression test checks.

Only rotation and (for attachments dispatched as "rigid") a Y-axis-only
translation are actually wired through to geometry in this phase, because
that's what the existing articulation_lib.py functions accept (a single
scalar "bob" for a uniform y-shift). Full [dx, dy] translation support in
transform_rigid/transform_two_joint would require changing those functions,
which this phase deliberately does not do - see the report for how this
limitation is expected to be lifted in a later phase without touching the
existing math today.
"""
import math

from .articulation_lib import (
    rotate_pt,
    precompute_weights,
    transform_two_joint,
    transform_rigid,
    transform_distal_rigid,
)


def zero_pose():
    return {}


def _rotation_delta(pose, bone_name):
    return float(pose.get(bone_name, {}).get("rotation", 0.0))


def _translation_delta(pose, bone_name):
    t = pose.get(bone_name, {}).get("translation")
    return [float(t[0]), float(t[1])] if t else [0.0, 0.0]


class TransformEvaluator:
    def __init__(self, model):
        """model: a CharacterLockModel (character_model.py)."""
        self.model = model
        self._weight_cache = {}  # attachment_name -> precomputed per-point weights

    # ------------------------------------------------------------------
    # Bone-level composition (generic, arbitrary depth)
    # ------------------------------------------------------------------
    def bone_world(self, bone_name, pose):
        """Returns (world_pivot=[x,y], world_rotation_deg, accumulated_pose_rotation_deg).

        world_rotation_deg includes each ancestor's rest_orientation_deg (the
        character's own baked-in rest geometry angles) and is only used to
        carry a moving parent's rotation into a child's WORLD PIVOT position.

        accumulated_pose_rotation_deg is the sum of pose-authored rotation
        deltas only (excluding rest_orientation_deg), because that is what
        must be fed as "theta" into the existing articulation_lib.py
        functions - those operate on already rest-oriented locked geometry
        and must not have rest_orientation re-applied on top.
        """
        bone = self.model.skeleton[bone_name]
        own_rotation_delta = _rotation_delta(pose, bone_name)
        own_translation_delta = _translation_delta(pose, bone_name)

        if bone.parent is None:
            world_rotation = bone.rest_orientation_deg + own_rotation_delta
            world_pivot = [bone.rest_pivot[0] + own_translation_delta[0],
                           bone.rest_pivot[1] + own_translation_delta[1]]
            return world_pivot, world_rotation, own_rotation_delta

        parent_pivot, parent_world_rotation, parent_accum_pose = self.bone_world(bone.parent, pose)
        parent_bone = self.model.skeleton[bone.parent]

        rest_offset = [bone.rest_pivot[0] - parent_bone.rest_pivot[0],
                       bone.rest_pivot[1] - parent_bone.rest_pivot[1]]
        rotated_offset = rotate_pt(rest_offset, [0.0, 0.0], parent_world_rotation)
        world_pivot = [parent_pivot[0] + rotated_offset[0] + own_translation_delta[0],
                       parent_pivot[1] + rotated_offset[1] + own_translation_delta[1]]

        world_rotation = parent_world_rotation + bone.rest_orientation_deg + own_rotation_delta
        accumulated_pose_rotation = parent_accum_pose + own_rotation_delta
        return world_pivot, world_rotation, accumulated_pose_rotation

    # ------------------------------------------------------------------
    # Attachment-level geometry transform (dispatches to articulation_lib.py)
    # ------------------------------------------------------------------
    def transform_attachment(self, attachment_name, pose, bob=0.0):
        """Returns {geometry_key: transformed_segments} for one attachment,
        by dispatching to the existing, unchanged articulation_lib.py
        functions based on the attachment's strategy.

        KNOWN LIMITATION (see final report, "architectural problems
        discovered"): articulation_lib.py's functions rotate the RAW LOCKED
        points directly around a supplied pivot; they do not additionally
        translate those raw points to account for an ANCESTOR bone having
        moved. bone_world() above correctly composes an arbitrarily deep,
        arbitrarily posed chain for BONE positions/rotations, but this
        geometry dispatch is only exact when every ancestor of an
        attachment's bone(s) is at zero pose (torso/root unposed) - which
        matches every existing validated use of walker2's character
        (torso never moves). Posing an ancestor (e.g. a future torso lean)
        and expecting correct attached-limb geometry is NOT yet solved here;
        doing so would require either extending articulation_lib.py's
        functions (explicitly out of scope this phase) or adding a
        translation step in front of them in a later phase.
        """
        attachment = self.model.attachments[attachment_name]
        comps = self.model.components_geometry
        out = {}

        if attachment.strategy == "rigid":
            bone_name = attachment.bones[0]
            world_pivot, _world_rotation, accum_rotation = self.bone_world(bone_name, pose)
            for geom_key in attachment.geometry:
                out[geom_key] = transform_rigid(comps[geom_key], world_pivot, accum_rotation, bob)
            for geom_key, child_bone in attachment.rigid_children.items():
                child_pivot, _cr, child_accum = self.bone_world(child_bone, pose)
                out[geom_key] = transform_rigid(comps[geom_key], child_pivot, child_accum, bob)
            return out

        if attachment.strategy == "soft_skin_2joint":
            proximal_bone, distal_bone = attachment.bones
            proximal_pivot, _pr, theta1 = self.bone_world(proximal_bone, pose)
            proximal_pivot_rest = self.model.skeleton[proximal_bone].rest_pivot
            distal_pivot_rest = self.model.skeleton[distal_bone].rest_pivot
            theta2 = _rotation_delta(pose, distal_bone)

            for geom_key in attachment.geometry:
                cache_key = (attachment_name, geom_key)
                if cache_key not in self._weight_cache:
                    # Weights are a pure function of the LOCKED rest geometry
                    # (never the current pose) - computed once from rest
                    # pivot/tip, exactly as precompute_weights already requires.
                    self._weight_cache[cache_key] = precompute_weights(
                        comps[geom_key], list(proximal_pivot_rest), list(distal_pivot_rest),
                    )
                weights = self._weight_cache[cache_key]
                out[geom_key] = transform_two_joint(
                    comps[geom_key], weights, proximal_pivot, list(distal_pivot_rest), theta1, theta2, bob,
                )

            for geom_key, rigid_bone in attachment.rigid_children.items():
                out[geom_key] = transform_distal_rigid(
                    comps[geom_key], proximal_pivot, list(distal_pivot_rest), theta1, theta2, bob,
                )
            return out

        raise ValueError(f"unknown transform strategy '{attachment.strategy}' on attachment '{attachment_name}'")

    def transform_all(self, pose, bob=0.0):
        """Returns {geometry_key: transformed_segments} across every
        attachment in the model - the full posed character, ready to be
        handed to a RendererAdapter (not implemented in this phase)."""
        out = {}
        for attachment_name in self.model.attachments:
            out.update(self.transform_attachment(attachment_name, pose, bob))
        return out
