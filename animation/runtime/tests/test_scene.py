from animation.runtime.character_asset import CharacterAsset
from animation.runtime.character_instance import CharacterInstance
from animation.runtime.scene import Scene
from animation.runtime.camera import Camera
from animation.runtime.actions import WalkAction, StandAction, SitAction

_ASSET = None


def _asset():
    global _ASSET
    if _ASSET is None:
        _ASSET = CharacterAsset.load()
    return _ASSET


def _walking_character(x=300.0):
    char = CharacterInstance(asset=_asset(), world_x=x, world_y=650.0)
    char.timeline.add(0, 10, WalkAction())
    return char


def _standing_character(x=800.0):
    char = CharacterInstance(asset=_asset(), world_x=x, world_y=650.0)
    char.timeline.add(0, 10, StandAction())
    return char


def test_instances_get_unique_ids_by_default():
    a = CharacterInstance(asset=_asset())
    b = CharacterInstance(asset=_asset())
    assert a.instance_id != b.instance_id


def test_multiple_characters_evaluate_independently():
    scene = Scene(duration=10, fps=24, camera=Camera())
    walker = _walking_character(x=300.0)
    stander = _standing_character(x=800.0)
    scene.add_character(walker)
    scene.add_character(stander)

    state = scene.evaluate(3.0)
    walker_pose = state[walker.instance_id]["pose"]
    stander_pose = state[stander.instance_id]["pose"]

    assert "thigh_front" in walker_pose.bones
    assert stander_pose.bone_rotation_map() == {}
    # Phase 2A: walking now advances world position (default speed=90,
    # direction=1) - the standing character's position is untouched.
    assert state[walker.instance_id]["position"] == (300.0 + 90.0 * 3.0, 650.0)
    assert state[stander.instance_id]["position"] == (800.0, 650.0)


def test_no_state_leakage_between_instances_of_same_asset():
    scene = Scene(duration=10, fps=24)
    walker = _walking_character()
    stander = _standing_character()
    scene.add_character(walker)
    scene.add_character(stander)

    scene.evaluate(1.0)
    scene.evaluate(4.999)
    state = scene.evaluate(7.0)

    # The standing character's pose must remain rest regardless of how many
    # times / at what times the walking character was evaluated.
    assert state[stander.instance_id]["pose"].bone_rotation_map() == {}


def test_scene_evaluate_is_pure_no_rendering_side_effects():
    scene = Scene(duration=5, fps=24)
    scene.add_character(_walking_character())
    # Calling evaluate repeatedly at the same time must be side-effect-free
    # and repeatable (no PNGs, no files, identical results).
    a = scene.evaluate(2.0)
    b = scene.evaluate(2.0)
    for cid in a:
        assert a[cid]["pose"].bone_rotation_map() == b[cid]["pose"].bone_rotation_map()


def test_frame_count_and_frame_times():
    scene = Scene(duration=10, fps=24)
    assert scene.frame_count() == 240
    times = list(scene.frame_times())
    assert times[0] == (0, 0.0)
    assert times[-1][0] == 239


def test_camera_independent_of_character_transforms():
    camera = Camera(x=999.0, y=999.0, zoom=2.0)
    scene = Scene(duration=1, fps=24, camera=camera)
    walker = _walking_character(x=42.0)
    scene.add_character(walker)
    state = scene.evaluate(0.0)
    assert state[walker.instance_id]["position"] == (42.0, 650.0)
    assert scene.camera.x == 999.0  # unaffected by character position
    assert scene.camera.zoom == 2.0


def test_sit_then_stand_sequencer_transition():
    char = CharacterInstance(asset=_asset(), world_x=500.0, world_y=650.0)
    char.timeline.add(0, 3, StandAction())
    char.timeline.add(3, 5, SitAction(), {"duration": 2.0, "mode": "down"})
    char.timeline.add(5, 7, SitAction(), {"duration": 0.001, "mode": "down"})  # hold seated
    char.timeline.add(7, 9, SitAction(), {"duration": 2.0, "mode": "up"})
    char.timeline.add(9, 10, StandAction())

    standing_pose = char.timeline.evaluate(1.0)
    mid_sit_pose = char.timeline.evaluate(6.0)
    standing_again_pose = char.timeline.evaluate(9.5)

    assert standing_pose.bones.get("root", None) is None or standing_pose.bones["root"].translation == (0.0, 0.0)
    assert mid_sit_pose.bones["root"].translation[1] > 50.0
    assert standing_again_pose.bone_rotation_map() == {}
