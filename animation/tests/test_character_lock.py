"""
A. Existing lock loads successfully.
B. Existing geometry checksum remains valid.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.character_model import CharacterLockModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def test_walker2_v1_loads_and_checksum_valid():
    """The ORIGINAL, un-migrated lock file must still load fine and its
    checksum must still validate - proving the migration never touched it."""
    m = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2.json"))
    assert m.components_geometry is not None
    assert m.checksum is not None
    assert m.checksum_valid()
    # v1 has no skeleton/attachments yet - must not error, must be empty
    assert m.skeleton == {}
    assert m.attachments == {}


def test_walker2_v2_loads_and_checksum_valid():
    m = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    assert m.checksum_valid()
    # every existing field preserved exactly
    assert set(m.components_geometry.keys()) == {
        "head", "torso", "front_upper_arm", "front_hand", "back_upper_arm",
        "back_hand", "front_leg", "front_foot", "back_leg", "back_foot",
    }
    assert m.pivots_px is not None
    assert m.hierarchy is not None
    assert m.measurements is not None
    assert m.ratios is not None


def test_hatshirt_v2_loads_and_checksum_valid():
    m = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_hatshirt_v2.json"))
    assert m.checksum_valid()
    assert len(m.components_geometry) == 25  # the 25 real (non-synthetic-joint) components from Part 6


def test_v1_and_v2_walker2_have_identical_geometry():
    """The migration must not have altered a single point of the traced
    geometry - only ADDED new top-level keys."""
    v1 = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2.json"))
    v2 = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    assert v1.components_geometry == v2.components_geometry
    assert v1.checksum == v2.checksum
    assert v1.pivots_px == v2.pivots_px
    assert v1.hierarchy == v2.hierarchy


if __name__ == "__main__":
    test_walker2_v1_loads_and_checksum_valid()
    test_walker2_v2_loads_and_checksum_valid()
    test_hatshirt_v2_loads_and_checksum_valid()
    test_v1_and_v2_walker2_have_identical_geometry()
    print("test_character_lock.py: all tests passed")
