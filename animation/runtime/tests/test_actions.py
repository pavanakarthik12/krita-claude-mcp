from animation.runtime.actions import IdleAction, WalkAction, StandAction, SitAction, WaveAction, TurnAction


def test_walk_is_deterministic():
    walk = WalkAction()
    p1 = walk.evaluate(0.137, {})
    p2 = walk.evaluate(0.137, {})
    assert p1.bone_rotation_map() == p2.bone_rotation_map()


def test_walk_evaluates_at_arbitrary_time():
    walk = WalkAction()
    # Must not raise / must produce a real pose at non-frame-aligned times.
    for t in (0.0, 0.137, 1.842, 100.001):
        pose = walk.evaluate(t, {})
        assert "thigh_front" in pose.bones


def test_walk_produces_coordinated_opposite_leg_phase():
    walk = WalkAction()
    pose = walk.evaluate(0.25, {"speed": 1.0})  # quarter cycle in
    thigh_f = pose.get_rotation("thigh_front")
    thigh_b = pose.get_rotation("thigh_back")
    # opposite-phase legs: front and back thigh angles should have opposite sign
    assert thigh_f * thigh_b <= 0.0


def test_walk_stride_speed_bounce_parameters_change_output():
    walk = WalkAction()
    base = walk.evaluate(0.3, {"speed": 1.0, "stride": 1.0, "bounce": 1.0})
    bigger_stride = walk.evaluate(0.3, {"speed": 1.0, "stride": 2.0, "bounce": 1.0})
    assert abs(bigger_stride.get_rotation("thigh_front")) > abs(base.get_rotation("thigh_front")) - 1e-6
    assert bigger_stride.get_rotation("thigh_front") != base.get_rotation("thigh_front")


def test_stand_is_rest_pose():
    stand = StandAction()
    pose = stand.evaluate(5.0, {})
    assert pose.bone_rotation_map() == {}


def test_sit_lowers_hip_and_bends_knees_over_time():
    sit = SitAction()
    start = sit.evaluate(0.0, {"duration": 1.0, "mode": "down"})
    end = sit.evaluate(1.0, {"duration": 1.0, "mode": "down"})

    assert start.bones["root"].translation[1] == 0.0
    assert end.bones["root"].translation[1] > 50.0  # hip has visibly lowered
    assert abs(end.get_rotation("thigh_front")) > abs(start.get_rotation("thigh_front"))
    assert abs(end.get_rotation("shin_front")) > abs(start.get_rotation("shin_front"))


def test_sit_up_reverses_sit_down():
    sit_down_end = SitAction().evaluate(1.0, {"duration": 1.0, "mode": "down"})
    sit_up_start = SitAction().evaluate(0.0, {"duration": 1.0, "mode": "up"})
    assert sit_down_end.bones["root"].translation[1] == sit_up_start.bones["root"].translation[1]

    sit_up_end = SitAction().evaluate(1.0, {"duration": 1.0, "mode": "up"})
    assert sit_up_end.bones["root"].translation[1] == 0.0


def test_wave_only_affects_chosen_arm():
    wave = WaveAction(arm="front")
    pose = wave.evaluate(0.1, {})
    assert set(pose.bones.keys()) == {"upper_arm_front", "forearm_front"}
    assert wave.affected_bones == ("upper_arm_front", "forearm_front")


def test_wave_back_arm_is_independent_bone_set():
    front = WaveAction(arm="front")
    back = WaveAction(arm="back")
    assert front.affected_bones != back.affected_bones


def test_turn_changes_heading_deterministically():
    turn = TurnAction(from_heading=1.0, to_heading=-1.0)
    early = turn.evaluate(0.0, {"duration": 1.0})
    late = turn.evaluate(1.0, {"duration": 1.0})
    assert early.heading == 1.0
    assert late.heading == -1.0


def test_idle_is_small_and_deterministic():
    idle = IdleAction()
    p1 = idle.evaluate(3.3, {})
    p2 = idle.evaluate(3.3, {})
    assert p1.bone_rotation_map() == p2.bone_rotation_map()
    assert abs(p1.get_rotation("torso")) < 5.0
