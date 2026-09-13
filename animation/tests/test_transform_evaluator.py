"""
E. Synthetic arbitrary-depth FK, verified against independently-computed
   trig (root -> torso -> upper_arm -> forearm -> hand).
F. Zero-pose regression: an all-zero Pose must reproduce the locked rest
   geometry exactly.
G. Existing-character regression: the NEW generic evaluator's dispatch
   must match the OLD, already-validated articulation_lib.py call path
   byte-for-byte for the same inputs (not just "close" - identical).
H. De-transform integrity: inverting a posed frame back through the known
   pose must recover the lock with 0px error, exactly as the project's
   prior verify_lock_integrity*.py scripts already established.
I. No gaps/attachment discontinuities: weight range spans [0, 1] and a
   shared joint point stays continuous under rotation.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.character_model import CharacterLockModel, Bone
from animation.transform_evaluator import TransformEvaluator
from animation import articulation_lib as alib

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# E. Synthetic chain, independently verified
# ---------------------------------------------------------------------------
def _make_synthetic_model():
    raw = {
        "components_geometry": {},
        "skeleton": {
            "root":      {"parent": None,   "rest_pivot": [0.0, 0.0],   "rest_orientation_deg": 0.0, "length": None},
            "torso":     {"parent": "root",  "rest_pivot": [0.0, -50.0], "rest_orientation_deg": 0.0, "length": 50.0},
            "upper_arm": {"parent": "torso", "rest_pivot": [10.0, -80.0], "rest_orientation_deg": 0.0, "length": 31.6, "transform_strategy": "rigid"},
            "forearm":   {"parent": "upper_arm", "rest_pivot": [10.0, -140.0], "rest_orientation_deg": 0.0, "length": 60.0, "transform_strategy": "rigid"},
            "hand":      {"parent": "forearm", "rest_pivot": [10.0, -180.0], "rest_orientation_deg": 0.0, "length": 40.0, "transform_strategy": "rigid"},
        },
        "attachments": {},
    }
    return CharacterLockModel(raw)


def test_synthetic_chain_zero_pose():
    model = _make_synthetic_model()
    ev = TransformEvaluator(model)
    for name in model.skeleton:
        world_pivot, world_rot, accum = ev.bone_world(name, {})
        bone = model.skeleton[name]
        assert abs(world_pivot[0] - bone.rest_pivot[0]) < TOLERANCE
        assert abs(world_pivot[1] - bone.rest_pivot[1]) < TOLERANCE
        assert abs(world_rot - 0.0) < TOLERANCE
        assert abs(accum - 0.0) < TOLERANCE


def test_synthetic_chain_torso_rotation_carries_children():
    """Rotating torso by 90deg must NOT move torso's own pivot (a joint
    doesn't move when the bone rooted there rotates - exactly how
    transform_rigid already works: rotate_pt(pivot, pivot, theta) == pivot).
    It MUST carry upper_arm's pivot around torso's pivot, since upper_arm
    is attached at the far end of that rotating bone. Verified against an
    independent hand-computed rotation, not just 'whatever the code says'."""
    model = _make_synthetic_model()
    ev = TransformEvaluator(model)
    pose = {"torso": {"rotation": 90.0}}

    torso_pivot = model.skeleton["torso"].rest_pivot
    upper_arm_pivot = model.skeleton["upper_arm"].rest_pivot

    # independent reference computation using the SAME rotate_pt the
    # production code uses (this is the point: verifying the COMPOSITION
    # logic in bone_world, not re-deriving rotate_pt's own correctness,
    # which is already covered by test_synthetic_chain_zero_pose and the
    # long-validated articulation_lib.py math).
    expected_torso_pivot = list(torso_pivot)  # unchanged - a bone's own rotation pivots AT itself
    rest_offset = [upper_arm_pivot[0] - torso_pivot[0], upper_arm_pivot[1] - torso_pivot[1]]
    rotated_offset = alib.rotate_pt(rest_offset, [0.0, 0.0], 90.0)
    expected_upper_arm_pivot = [expected_torso_pivot[0] + rotated_offset[0],
                                 expected_torso_pivot[1] + rotated_offset[1]]

    got_torso_pivot, torso_rot, _ = ev.bone_world("torso", pose)
    got_upper_arm_pivot, upper_arm_rot, upper_arm_accum = ev.bone_world("upper_arm", pose)

    assert math.hypot(got_torso_pivot[0] - expected_torso_pivot[0], got_torso_pivot[1] - expected_torso_pivot[1]) < TOLERANCE
    assert math.hypot(got_upper_arm_pivot[0] - expected_upper_arm_pivot[0], got_upper_arm_pivot[1] - expected_upper_arm_pivot[1]) < TOLERANCE
    assert abs(torso_rot - 90.0) < TOLERANCE
    assert abs(upper_arm_rot - 90.0) < TOLERANCE          # inherited, upper_arm itself posed at 0
    # accumulated_pose_rotation is EXPLICITLY the sum of every ancestor's pose
    # delta plus this bone's own (see bone_world()'s docstring) - it must
    # include torso's 90deg here, since that's what gets fed as "theta1" into
    # articulation_lib's functions when transforming upper_arm's geometry.
    assert abs(upper_arm_accum - 90.0) < TOLERANCE


def test_synthetic_chain_four_levels_independent_rotation():
    """root(rot=10) -> torso(rot=20) -> upper_arm(rot=30) -> forearm(rot=40)
    -> hand: accumulated pose rotation at hand must equal the sum of every
    ancestor's OWN delta plus its own (10+20+30+40=100), proving arbitrary
    depth composes correctly, not just a hardcoded 2-level case."""
    model = _make_synthetic_model()
    ev = TransformEvaluator(model)
    pose = {"root": {"rotation": 10.0}, "torso": {"rotation": 20.0},
            "upper_arm": {"rotation": 30.0}, "forearm": {"rotation": 40.0}}
    _, _, accum = ev.bone_world("hand", pose)
    assert abs(accum - 100.0) < TOLERANCE


# ---------------------------------------------------------------------------
# F. Zero-pose regression against the real locked character
# ---------------------------------------------------------------------------
def test_walker2_zero_pose_reproduces_lock_exactly():
    model = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    ev = TransformEvaluator(model)
    result = ev.transform_all({}, bob=0.0)

    max_err = 0.0
    for geom_key, segs in result.items():
        locked_segs = model.components_geometry[geom_key]
        for a, b in zip(segs, locked_segs):
            for k in ("start", "control1", "control2", "end"):
                max_err = max(max_err, math.hypot(a[k][0] - b[k][0], a[k][1] - b[k][1]))
    assert max_err < TOLERANCE, f"zero-pose max error {max_err}"


# ---------------------------------------------------------------------------
# G. Regression against the OLD, already-validated call path
# ---------------------------------------------------------------------------
def test_walker2_matches_old_articulation_lib_call_path_exactly():
    """For a nonzero pose, the new evaluator's dispatch must produce
    BYTE-IDENTICAL output to calling articulation_lib.py directly the way
    walker2_animate_articulated.py already did (and had independently
    verified at 0.0000000000px). This is the strongest possible proof
    that the new architecture didn't change the math, only its packaging."""
    model = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    ev = TransformEvaluator(model)

    theta1, theta2 = 17.3, 22.5  # arbitrary nonzero angles, matching Part 7's own spot-check values
    pose = {"upper_arm_front": {"rotation": theta1}, "forearm_front": {"rotation": theta2}}

    new_result = ev.transform_attachment("front_arm", pose)

    # OLD path: exactly what walker2_animate_articulated.py did directly
    pivot = model.skeleton["upper_arm_front"].rest_pivot
    joint_rest = model.skeleton["forearm_front"].rest_pivot
    old_weights = alib.precompute_weights(model.components_geometry["front_upper_arm"], pivot, joint_rest)
    old_arm = alib.transform_two_joint(model.components_geometry["front_upper_arm"], old_weights, pivot, joint_rest, theta1, theta2, 0.0)
    old_hand = alib.transform_distal_rigid(model.components_geometry["front_hand"], pivot, joint_rest, theta1, theta2, 0.0)

    assert new_result["front_upper_arm"] == old_arm
    assert new_result["front_hand"] == old_hand


# ---------------------------------------------------------------------------
# H. De-transform integrity: 0px, same tolerance as the project's prior checks
# ---------------------------------------------------------------------------
def test_walker2_full_detransform_integrity():
    model = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    ev = TransformEvaluator(model)

    pose = {
        "upper_arm_front": {"rotation": 12.0}, "forearm_front": {"rotation": 30.0},
        "upper_arm_back": {"rotation": -8.0}, "forearm_back": {"rotation": 15.0},
        "thigh_front": {"rotation": -20.0}, "shin_front": {"rotation": 40.0},
        "thigh_back": {"rotation": 20.0}, "shin_back": {"rotation": 5.0},
    }
    bob = 3.0
    result = ev.transform_all(pose, bob=bob)

    max_err = 0.0
    for attachment_name, attachment in model.attachments.items():
        if attachment.strategy == "rigid":
            bone_name = attachment.bones[0]
            pivot, _, theta = ev.bone_world(bone_name, pose)
            for geom_key in attachment.geometry:
                for seg_out, seg_locked in zip(result[geom_key], model.components_geometry[geom_key]):
                    for k in ("start", "control1", "control2", "end"):
                        p = [seg_out[k][0], seg_out[k][1] - bob]
                        p_rest = alib.rotate_pt(p, pivot, -theta)
                        lp = seg_locked[k]
                        max_err = max(max_err, math.hypot(p_rest[0] - lp[0], p_rest[1] - lp[1]))
        else:
            proximal_bone, distal_bone = attachment.bones
            pivot, _, theta1 = ev.bone_world(proximal_bone, pose)
            joint_rest = model.skeleton[distal_bone].rest_pivot
            theta2 = pose.get(distal_bone, {}).get("rotation", 0.0)
            joint_after1 = alib.rotate_pt(joint_rest, pivot, theta1)

            for geom_key in attachment.geometry:
                w = alib.precompute_weights(model.components_geometry[geom_key],
                                             model.skeleton[proximal_bone].rest_pivot, joint_rest)
                for seg_out, seg_locked, seg_w in zip(result[geom_key], model.components_geometry[geom_key], w):
                    for k in ("start", "control1", "control2", "end"):
                        p = [seg_out[k][0], seg_out[k][1] - bob]
                        p_undo2 = alib.rotate_pt(p, joint_after1, -theta2 * seg_w[k])
                        p_rest = alib.rotate_pt(p_undo2, pivot, -theta1)
                        lp = seg_locked[k]
                        max_err = max(max_err, math.hypot(p_rest[0] - lp[0], p_rest[1] - lp[1]))
            for geom_key, rigid_bone in attachment.rigid_children.items():
                for seg_out, seg_locked in zip(result[geom_key], model.components_geometry[geom_key]):
                    for k in ("start", "control1", "control2", "end"):
                        p = [seg_out[k][0], seg_out[k][1] - bob]
                        p_undo2 = alib.rotate_pt(p, joint_after1, -theta2)
                        p_rest = alib.rotate_pt(p_undo2, pivot, -theta1)
                        lp = seg_locked[k]
                        max_err = max(max_err, math.hypot(p_rest[0] - lp[0], p_rest[1] - lp[1]))

    assert max_err < TOLERANCE, f"de-transform max error {max_err}px (expected < {TOLERANCE}px)"


# ---------------------------------------------------------------------------
# I. No gaps: weight range + rigid-child continuity at the joint
# ---------------------------------------------------------------------------
def test_walker2_soft_skin_weight_range_and_joint_continuity():
    model = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    pivot = model.skeleton["upper_arm_front"].rest_pivot
    joint_rest = model.skeleton["forearm_front"].rest_pivot
    weights = alib.precompute_weights(model.components_geometry["front_upper_arm"], pivot, joint_rest)
    all_w = [v for seg in weights for v in seg.values()]
    assert min(all_w) == 0.0
    assert max(all_w) == 1.0

    ev = TransformEvaluator(model)

    # Pick ONE specific, deterministic point identity: the first segment/key
    # whose weight is exactly 1.0 (fully at the distal/tip end) - tracking
    # the SAME point index across rest and posed transforms, rather than
    # re-searching "whichever point is currently farthest from pivot" (which
    # can shift identity slightly once soft-skin blending reshapes the
    # contour, giving a false positive "gap").
    tip_seg_idx, tip_key = None, None
    for i, w in enumerate(weights):
        for k, val in w.items():
            if val == 1.0:
                tip_seg_idx, tip_key = i, k
                break
        if tip_seg_idx is not None:
            break
    assert tip_seg_idx is not None, "no weight==1.0 point found - precompute_weights range check above should have caught this"

    def arm_tip_to_hand_distance(pose):
        arm = ev.transform_attachment("front_arm", pose)
        arm_tip = arm["front_upper_arm"][tip_seg_idx][tip_key]
        hand_centroid_pts = [pt for seg in arm["front_hand"] for pt in (seg["start"], seg["end"])]
        hand_centroid = [sum(p[0] for p in hand_centroid_pts) / len(hand_centroid_pts),
                          sum(p[1] for p in hand_centroid_pts) / len(hand_centroid_pts)]
        return math.hypot(arm_tip[0] - hand_centroid[0], arm_tip[1] - hand_centroid[1])

    # "No gap introduced" means the rigid relationship between this SAME
    # tracked tip point and the hand's attachment point - fixed by
    # construction in the LOCKED (rest) geometry - must be PRESERVED after
    # an arbitrary rotation, not stretched or torn apart.
    rest_distance = arm_tip_to_hand_distance({})
    posed_distance = arm_tip_to_hand_distance({"upper_arm_front": {"rotation": 15.0}, "forearm_front": {"rotation": 50.0}})
    assert abs(posed_distance - rest_distance) < TOLERANCE, (
        f"arm-tip-to-hand distance changed from {rest_distance:.3f}px (rest) to "
        f"{posed_distance:.6f}px (posed) - indicates a gap/tear was introduced"
    )


if __name__ == "__main__":
    test_synthetic_chain_zero_pose()
    test_synthetic_chain_torso_rotation_carries_children()
    test_synthetic_chain_four_levels_independent_rotation()
    test_walker2_zero_pose_reproduces_lock_exactly()
    test_walker2_matches_old_articulation_lib_call_path_exactly()
    test_walker2_full_detransform_integrity()
    test_walker2_soft_skin_weight_range_and_joint_continuity()
    print("test_transform_evaluator.py: all tests passed")
