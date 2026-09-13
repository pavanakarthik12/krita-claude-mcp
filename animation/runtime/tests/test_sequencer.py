from animation.runtime.sequencer import Sequencer
from animation.runtime.actions import IdleAction, WalkAction, StandAction, WaveAction


def test_sequencer_picks_correct_action_per_segment():
    seq = Sequencer()
    seq.add(0, 2, IdleAction())
    seq.add(2, 5, WalkAction())
    seq.add(5, 6, StandAction())

    idle_pose = seq.evaluate(1.0)
    walk_pose = seq.evaluate(3.0)
    stand_pose = seq.evaluate(5.5)

    assert stand_pose.bone_rotation_map() == {}
    # walk pose should have a nonzero thigh angle somewhere in its cycle or
    # at least differ structurally from idle's bone set
    assert "thigh_front" in walk_pose.bones
    assert "thigh_front" not in idle_pose.bones


def test_sequencer_local_time_resets_per_segment():
    seq = Sequencer()
    seq.add(0, 5, WalkAction())
    seq.add(5, 10, WalkAction())

    # Same local offset into each segment (0.3s in) must produce identical
    # poses, proving the sequencer passes LOCAL time, not global time, to
    # the action.
    pose_a = seq.evaluate(0.3)
    pose_b = seq.evaluate(5.3)
    map_a, map_b = pose_a.bone_rotation_map(), pose_b.bone_rotation_map()
    assert map_a.keys() == map_b.keys()
    for bone in map_a:
        assert abs(map_a[bone] - map_b[bone]) < 1e-6


def test_sequencer_overlay_blends_only_masked_bones():
    seq = Sequencer()
    seq.add(0, 10, WalkAction())
    seq.add_overlay(2, 6, WaveAction(arm="front"))

    walking_only = seq.evaluate(1.0)  # before overlay starts
    walking_with_wave = seq.evaluate(3.0)  # overlay active

    # legs still driven by the base walk action during the overlay window
    assert "thigh_front" in walking_with_wave.bones
    assert "thigh_front" in walking_only.bones

    # the overlaid arm no longer matches the base walk's own arm angle
    base_only_pose = WalkAction().evaluate(3.0, {})
    assert walking_with_wave.get_rotation("upper_arm_front") != base_only_pose.get_rotation("upper_arm_front")
    # the un-overlaid arm (back) is untouched by the overlay
    assert walking_with_wave.get_rotation("upper_arm_back") == base_only_pose.get_rotation("upper_arm_back")

    # outside the overlay window, no wave influence
    assert walking_only.get_rotation("upper_arm_front") == WalkAction().evaluate(1.0, {}).get_rotation("upper_arm_front")


def test_sequencer_clamps_before_and_after_range():
    seq = Sequencer()
    seq.add(2, 5, WalkAction())
    before = seq.evaluate(-3.0)  # before the only segment
    after = seq.evaluate(50.0)   # long after the only segment
    assert before.bone_rotation_map() == WalkAction().evaluate(0.0, {}).bone_rotation_map()
    assert after.bone_rotation_map() == WalkAction().evaluate(3.0, {}).bone_rotation_map()  # clamped to seg.end - seg.start


def test_sequencer_is_deterministic():
    seq = Sequencer()
    seq.add(0, 2, IdleAction())
    seq.add(2, 5, WalkAction())
    p1 = seq.evaluate(3.456)
    p2 = seq.evaluate(3.456)
    assert p1.bone_rotation_map() == p2.bone_rotation_map()
