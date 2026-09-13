"""
Minimal Pose representation - the only input TransformEvaluator needs.

This is deliberately NOT the Action system (no procedural pose generators,
no keyframes, no sequencing - those are later phases). A Pose is just a
plain dict:

    {
        bone_name: {
            "rotation": degrees,        # delta from that bone's rest orientation
            "translation": [dx, dy],    # optional; world-space offset
        },
        ...
    }

Bones not mentioned are implicitly at rest (rotation=0, translation=[0,0]).
"""


def zero_pose():
    """The rest pose: every bone at its locked, untransformed orientation."""
    return {}


def make_pose(**bone_deltas):
    """make_pose(upper_arm_front={"rotation": 20.0}) -> {"upper_arm_front": {"rotation": 20.0}}
    Convenience constructor; a plain dict literal works identically."""
    return dict(bone_deltas)


def validate_pose(pose, model):
    """Returns a list of problem strings; empty = valid. Checks every bone
    named in the pose actually exists in the model's skeleton, and that
    rotation/translation values are numeric - nothing more (no joint-limit
    clamping in this phase, see the constraint system in a later phase)."""
    problems = []
    for bone_name, delta in pose.items():
        if bone_name not in model.skeleton:
            problems.append(f"pose references unknown bone '{bone_name}'")
            continue
        if "rotation" in delta:
            try:
                float(delta["rotation"])
            except (TypeError, ValueError):
                problems.append(f"bone '{bone_name}' rotation is not numeric: {delta['rotation']!r}")
        if "translation" in delta:
            t = delta["translation"]
            if not (isinstance(t, (list, tuple)) and len(t) == 2):
                problems.append(f"bone '{bone_name}' translation must be [dx, dy]: {t!r}")
    return problems
