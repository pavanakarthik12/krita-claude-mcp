from animation.runtime.character_asset import CharacterAsset


def test_asset_loads_from_poc4_generated_files():
    asset = CharacterAsset.load()
    assert asset.name == "walker2"
    assert len(asset.bone_names) == 11
    assert "thigh_front" in asset.bone_names
    assert "root" in asset.bone_names


def test_asset_exposes_mesh_and_rigid_part_names():
    asset = CharacterAsset.load()
    assert set(asset.mesh_slot_names) == {"front_leg", "back_leg", "front_upper_arm", "back_upper_arm"}
    assert set(asset.rigid_part_names) == {"head", "torso", "front_hand", "back_hand", "front_foot", "back_foot"}


def test_asset_available_actions():
    asset = CharacterAsset.load()
    for name in ("idle", "walk", "stand", "sit", "wave", "turn"):
        assert name in asset.available_actions


def test_asset_dimensions():
    asset = CharacterAsset.load()
    dims = asset.dimensions()
    assert "root_x" in dims and "root_y" in dims


def test_multiple_loads_do_not_duplicate_or_mutate_the_lock():
    import json
    asset1 = CharacterAsset.load()
    with open(asset1.character_lock_path) as f:
        before = json.load(f)
    asset2 = CharacterAsset.load()
    with open(asset2.character_lock_path) as f:
        after = json.load(f)
    assert before == after  # loading the asset never touches the Character Lock file
