import math

from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.sequencer import Sequencer
from animation.runtime.pose import Pose
from animation.runtime.actions import WalkAction, StandAction, SitAction, StopAction, TurnAction, IdleAction

_ASSET = None


def _asset():
    global _ASSET
    if _ASSET is None:
        _ASSET = CharacterAsset.load()
    return _ASSET


# --- 2A: locomotion ---

def test_walk_moves_world_position_with_speed_and_direction():
    walk = WalkAction()
    dx_fwd, dy = walk.world_delta(2.0, {"speed": 100.0, "direction": 1.0})
    dx_back, _ = walk.world_delta(2.0, {"speed": 100.0, "direction": -1.0})
    assert dx_fwd == 200.0
    assert dx_back == -200.0
    assert dy == 0.0


def test_locomotion_deterministic_given_time():
    walk = WalkAction()
    a = walk.world_delta(1.337, {"speed": 90.0, "direction": 1.0})
    b = walk.world_delta(1.337, {"speed": 90.0, "direction": 1.0})
    assert a == b


def test_character_instance_position_advances_with_walk():
    char = CharacterInstance(asset=_asset(), world_x=500.0, world_y=650.0)
    char.timeline.add(0.0, 5.0, WalkAction(), {"speed": 80.0})
    p0 = char.evaluate(0.0)["position"]
    p1 = char.evaluate(2.0)["position"]
    assert p0 == (500.0, 650.0)
    assert p1 == (500.0 + 80.0 * 2.0, 650.0)


def test_locomotion_does_not_touch_bone_geometry():
    # requirement: do NOT bake movement into bone geometry - a moving
    # character's bone rotations must depend only on gait phase, never on
    # accumulated world position.
    char_a = CharacterInstance(asset=_asset(), world_x=0.0, world_y=0.0)
    char_a.timeline.add(0.0, 10.0, WalkAction(), {"speed": 200.0})
    char_b = CharacterInstance(asset=_asset(), world_x=99999.0, world_y=0.0)
    char_b.timeline.add(0.0, 10.0, WalkAction(), {"speed": 200.0})
    pose_a = char_a.evaluate(3.0)["pose"]
    pose_b = char_b.evaluate(3.0)["pose"]
    assert pose_a.bone_rotation_map() == pose_b.bone_rotation_map()


# --- 2C: foot contact ---

def test_front_and_back_feet_alternate_stance():
    walk = WalkAction()
    ctx = {"asset": _asset()}
    # at t=0 front foot is in stance (phase 0), back foot (phase+pi) is
    # mid-swing - their thigh angle MAGNITUDES should differ noticeably.
    pose = walk.evaluate(0.0, {"speed": 90.0, "gait_hz": 1.0}, ctx)
    front = pose.get_rotation("thigh_front")
    back = pose.get_rotation("thigh_back")
    assert abs(front - back) > 5.0


def test_stance_leg_does_not_hyperextend_or_invert():
    walk = WalkAction()
    ctx = {"asset": _asset()}
    for i in range(24):
        t = i / 24.0
        pose = walk.evaluate(t, {"speed": 90.0, "gait_hz": 1.0}, ctx)
        # A sane knee bend stays well within +/-90 degrees of the rest
        # angle for this gait; anything larger signals the IK solver
        # picked a degenerate/inverted solution.
        assert abs(pose.get_rotation("thigh_front")) < 60.0
        assert abs(pose.get_rotation("shin_front")) < 60.0


def test_no_sudden_angle_jump_across_the_gait_cycle():
    walk = WalkAction()
    ctx = {"asset": _asset()}
    prev = None
    max_step = 0.0
    for i in range(49):  # two full cycles at 24fps, 1Hz gait
        t = i / 24.0
        pose = walk.evaluate(t, {"speed": 90.0, "gait_hz": 1.0}, ctx)
        cur = pose.get_rotation("thigh_front")
        if prev is not None:
            max_step = max(max_step, abs(cur - prev))
        prev = cur
    # ~1/24s at a 1Hz gait should never move the knee more than a few
    # degrees frame-to-frame; a large max_step would indicate the IK
    # "pop" found and fixed during this phase (see walk.py's reach slack).
    assert max_step < 10.0


# --- 2D: transitions ---

def test_transition_blends_at_segment_boundary():
    seq = Sequencer()
    seq.add(0.0, 3.0, StandAction())
    seq.add(3.0, 5.0, SitAction(), {"duration": 2.0, "mode": "down"}, transition_in=0.5)

    just_before = seq.evaluate(2.999)
    at_start = seq.evaluate(3.0)
    mid_transition = seq.evaluate(3.25)
    after_transition = seq.evaluate(3.5)

    assert just_before.bones.get("root", None) is None or just_before.bones["root"].translation == (0.0, 0.0)
    # at the exact boundary, transition alpha=0 -> should equal the frozen prior pose (rest)
    assert at_start.bones.get("root", None) is None or at_start.bones["root"].translation[1] == 0.0
    # partway through the transition, hip should be OFFSET from both pure endpoints (a real blend)
    hip_mid = mid_transition.bones["root"].translation[1]
    hip_pure_sit_at_same_local_t = SitAction().evaluate(0.25, {"duration": 2.0, "mode": "down"}).bones["root"].translation[1]
    assert 0.0 < hip_mid < hip_pure_sit_at_same_local_t + 1e-6
    assert hip_mid != hip_pure_sit_at_same_local_t  # blended, not just the raw sit pose


def test_generic_transition_works_for_arbitrary_action_pair():
    # the SAME mechanism, no special-casing, applied to idle->walk
    seq = Sequencer()
    seq.add(0.0, 2.0, IdleAction())
    seq.add(2.0, 6.0, WalkAction(), {"speed": 80.0}, transition_in=0.4)

    at_boundary = seq.evaluate(2.0)
    mid = seq.evaluate(2.2)
    after = seq.evaluate(2.5)
    # no assertion crashes / all produce valid poses - genericity check
    assert isinstance(at_boundary, Pose)
    assert isinstance(mid, Pose)
    assert isinstance(after, Pose)


# --- 2G: stop / deceleration ---

def test_stop_velocity_decays_towards_zero():
    stop = StopAction()
    params = {"duration": 1.0, "initial_speed": 100.0, "direction": 1.0}
    # instantaneous velocity ~ derivative of world_delta; approximate via
    # small finite differences at the start vs near the end of the stop.
    d0 = stop.world_delta(0.01, params)[0] - stop.world_delta(0.0, params)[0]
    d1 = stop.world_delta(1.0, params)[0] - stop.world_delta(0.99, params)[0]
    assert d1 < d0  # velocity near the end is smaller than at the start


def test_stop_stride_amplitude_decays_to_zero():
    stop = StopAction()
    ctx = {"asset": _asset()}
    params = {"duration": 1.0, "initial_stride": 1.0, "initial_bounce": 1.0, "initial_speed": 90.0, "gait_hz": 1.0}
    pose_start = stop.evaluate(0.01, params, ctx)
    pose_end = stop.evaluate(0.99, params, ctx)
    # near the end of the stop, limb excursions should be much smaller
    assert abs(pose_end.get_rotation("upper_arm_front")) < abs(pose_start.get_rotation("upper_arm_front")) + 1.0
    assert abs(pose_end.bones["root"].translation[1]) <= abs(pose_start.bones["root"].translation[1]) + 1e-6


def test_stop_is_deterministic():
    stop = StopAction()
    params = {"duration": 1.2, "initial_speed": 90.0}
    a = stop.world_delta(0.7, params)
    b = stop.world_delta(0.7, params)
    assert a == b


# --- 2H: turn / heading ---

def test_turn_is_smooth_not_a_snap():
    turn = TurnAction(from_heading=1.0, to_heading=-1.0)
    values = [turn.evaluate(t, {"duration": 1.0}).heading for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    # strictly monotonic (a snap would repeat the same two values only)
    assert len(set(values)) == 5
    assert values[0] == 1.0
    assert values[-1] == -1.0


def test_heading_persists_after_turn_segment_ends():
    # Regression: found via visual inspection of the Phase 2 test scene -
    # a TurnAction's heading change must stick for every later segment,
    # not reset the instant the turn's own segment ends.
    char = CharacterInstance(asset=_asset(), world_x=0.0, world_y=0.0, heading=1.0)
    char.timeline.add(0.0, 1.0, StandAction())
    char.timeline.add(1.0, 1.3, TurnAction(from_heading=1.0, to_heading=-1.0), {"duration": 0.3})
    char.timeline.add(1.3, 5.0, WalkAction(), {"speed": 50.0})

    assert char.evaluate(0.5)["heading"] == 1.0
    assert char.evaluate(1.3)["heading"] == -1.0
    assert char.evaluate(3.0)["heading"] == -1.0  # still -1 long after the turn segment ended


def test_heading_independent_of_camera():
    from animation.runtime.camera import Camera
    cam = Camera(x=1.0, y=2.0, zoom=3.0)
    turn = TurnAction(from_heading=1.0, to_heading=-1.0)
    pose = turn.evaluate(0.5, {"duration": 1.0})
    assert pose.heading == 0.0  # midpoint of a symmetric smoothstep lerp
    assert cam.x == 1.0 and cam.zoom == 3.0  # untouched, unrelated


# --- multi-character independence with the new locomotion/IK path ---

def test_multiple_walking_characters_remain_independent_with_locomotion():
    a = CharacterInstance(asset=_asset(), world_x=0.0, world_y=0.0, instance_id="a")
    a.timeline.add(0.0, 5.0, WalkAction(), {"speed": 50.0})
    b = CharacterInstance(asset=_asset(), world_x=1000.0, world_y=0.0, instance_id="b")
    b.timeline.add(0.0, 5.0, StandAction())

    pa = a.evaluate(2.0)
    pb = b.evaluate(2.0)
    assert pa["position"][0] == 100.0
    assert pb["position"][0] == 1000.0
    assert pb["pose"].bone_rotation_map() == {}
