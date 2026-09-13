"""Requirement 19: 'same scene + same timestamp -> identical pose'."""
from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.scene import Scene
from animation.runtime.actions import IdleAction, WalkAction, StandAction, SitAction, WaveAction


def _build_scene():
    asset = CharacterAsset.load()
    scene = Scene(duration=10, fps=24)

    c1 = CharacterInstance(asset=asset, world_x=300.0, world_y=650.0, instance_id="c1")
    c1.timeline.add(0, 2, IdleAction())
    c1.timeline.add(2, 5, WalkAction())
    c1.timeline.add(5, 6, StandAction())
    c1.timeline.add(6, 8, StandAction())
    c1.timeline.add_overlay(6, 8, WaveAction(arm="front"))
    c1.timeline.add(8, 10, WalkAction())

    c2 = CharacterInstance(asset=asset, world_x=800.0, world_y=650.0, instance_id="c2")
    c2.timeline.add(0, 3, StandAction())
    c2.timeline.add(3, 5, SitAction(), {"duration": 2.0, "mode": "down"})
    c2.timeline.add(5, 7, SitAction(), {"duration": 0.01, "mode": "down"})
    c2.timeline.add(7, 9, SitAction(), {"duration": 2.0, "mode": "up"})
    c2.timeline.add(9, 10, StandAction())

    scene.add_character(c1)
    scene.add_character(c2)
    return scene


def test_two_independently_built_scenes_agree_at_every_sampled_time():
    scene_a = _build_scene()
    scene_b = _build_scene()
    for t in [0.0, 0.5, 1.999, 2.0, 3.456, 5.0, 5.999, 6.5, 7.999, 8.0, 9.9999]:
        state_a = scene_a.evaluate(t)
        state_b = scene_b.evaluate(t)
        for cid in state_a:
            assert state_a[cid]["pose"].bone_rotation_map() == state_b[cid]["pose"].bone_rotation_map(), \
                f"mismatch for {cid} at t={t}"
            assert state_a[cid]["position"] == state_b[cid]["position"]
            assert state_a[cid]["heading"] == state_b[cid]["heading"]


def test_repeated_evaluation_of_same_scene_is_stable():
    scene = _build_scene()
    for t in [0.137, 4.2, 6.6, 8.8]:
        first = scene.evaluate(t)
        second = scene.evaluate(t)
        for cid in first:
            assert first[cid]["pose"].bone_rotation_map() == second[cid]["pose"].bone_rotation_map()


def test_action_transitions_are_correct_at_boundaries():
    scene = _build_scene()
    state = scene.evaluate(2.0)  # exactly the idle->walk boundary
    assert "thigh_front" in state["c1"]["pose"].bones  # walk has begun, not idle

    state = scene.evaluate(1.9999)
    assert "thigh_front" not in state["c1"]["pose"].bones  # still idle


def test_walk_changes_position_deterministically():
    # Phase 2A: walking now advances world position through a SEPARATE
    # channel (Action.world_delta), never baked into bone geometry - c1's
    # walk segment runs from t=2 to t=5 at the default speed (90 units/s),
    # so position at any t in that window is a pure, predictable function
    # of elapsed local time, and re-evaluating the same scene/time always
    # agrees.
    scene_a = _build_scene()
    scene_b = _build_scene()

    p_before = scene_a.evaluate(2.0)["c1"]["position"]
    p_mid = scene_a.evaluate(4.0)["c1"]["position"]
    assert p_before == (300.0, 650.0)  # walk hasn't started moving yet
    assert p_mid == (300.0 + 90.0 * 2.0, 650.0)  # 2s into the walk segment

    assert scene_a.evaluate(4.0)["c1"]["position"] == scene_b.evaluate(4.0)["c1"]["position"]
