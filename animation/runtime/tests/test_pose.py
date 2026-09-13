from animation.runtime.pose import Pose


def test_identity_pose_is_empty():
    pose = Pose.identity()
    assert pose.bones == {}
    assert pose.get_rotation("thigh_front") == 0.0


def test_set_and_get_rotation():
    pose = Pose()
    pose.set_rotation("thigh_front", 12.5)
    assert pose.get_rotation("thigh_front") == 12.5
    assert pose.get_rotation("shin_front") == 0.0


def test_bone_rotation_map():
    pose = Pose()
    pose.set_rotation("a", 1.0)
    pose.set_rotation("b", 2.0)
    assert pose.bone_rotation_map() == {"a": 1.0, "b": 2.0}


def test_merge_only_touches_masked_bones():
    base = Pose()
    base.set_rotation("thigh_front", 10.0)
    base.set_rotation("upper_arm_front", 5.0)

    overlay = Pose()
    overlay.set_rotation("upper_arm_front", 99.0)
    overlay.set_rotation("forearm_front", 88.0)

    merged = Pose.merge(base, overlay, ("upper_arm_front", "forearm_front"))

    assert merged.get_rotation("thigh_front") == 10.0  # untouched
    assert merged.get_rotation("upper_arm_front") == 99.0  # overridden
    assert merged.get_rotation("forearm_front") == 88.0  # added by overlay


def test_merge_ignores_overlay_bones_outside_mask():
    base = Pose()
    base.set_rotation("thigh_front", 10.0)

    overlay = Pose()
    overlay.set_rotation("thigh_front", 999.0)  # overlay tries to set an unmasked bone

    merged = Pose.merge(base, overlay, ("upper_arm_front",))
    assert merged.get_rotation("thigh_front") == 10.0  # overlay's value ignored
