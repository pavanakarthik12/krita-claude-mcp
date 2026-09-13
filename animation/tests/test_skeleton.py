"""
C. Skeleton loads.
D. Parent-child relationships are valid.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from animation.character_model import CharacterLockModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def test_walker2_skeleton_structure():
    m = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_walker2_v2.json"))
    assert m.validate_skeleton() == []
    assert len(m.root_bones()) == 1
    assert m.root_bones()[0].name == "root"
    # arbitrary-depth chain actually present: root -> torso -> upper_arm_front -> forearm_front
    forearm = m.skeleton["forearm_front"]
    assert forearm.parent == "upper_arm_front"
    assert m.skeleton["upper_arm_front"].parent == "torso"
    assert m.skeleton["torso"].parent == "root"
    assert m.skeleton["root"].parent is None


def test_hatshirt_skeleton_structure_and_depth():
    m = CharacterLockModel.from_file(os.path.join(DATA_DIR, "character_lock_hatshirt_v2.json"))
    assert m.validate_skeleton() == []
    assert len(m.root_bones()) == 1

    # genuine >=4-level chain, from real data (not synthetic): hat_crown -> hat_brim -> head -> neck -> torso_placket -> root
    chain = []
    cur = "hat_crown"
    while cur is not None:
        chain.append(cur)
        cur = m.skeleton[cur].parent
    assert chain == ["hat_crown", "hat_brim", "head", "neck", "torso_placket", "root"]
    assert len(chain) >= 4 + 1  # at least 4 parent hops, satisfying arbitrary-depth requirement


def test_no_orphan_or_cyclic_bones():
    for fname in ("character_lock_walker2_v2.json", "character_lock_hatshirt_v2.json"):
        m = CharacterLockModel.from_file(os.path.join(DATA_DIR, fname))
        problems = m.validate_skeleton()
        assert problems == [], f"{fname}: {problems}"


def test_attachments_reference_real_bones_and_geometry():
    for fname in ("character_lock_walker2_v2.json", "character_lock_hatshirt_v2.json"):
        m = CharacterLockModel.from_file(os.path.join(DATA_DIR, fname))
        for name, att in m.attachments.items():
            for b in att.bones:
                assert b in m.skeleton, f"{fname}: attachment '{name}' references unknown bone '{b}'"
            for g in att.geometry:
                assert g in m.components_geometry, f"{fname}: attachment '{name}' references unknown geometry '{g}'"
            for child_geom, child_bone in att.rigid_children.items():
                assert child_bone in m.skeleton, f"{fname}: attachment '{name}' rigid_child bone '{child_bone}' unknown"
                assert child_geom in m.components_geometry, f"{fname}: attachment '{name}' rigid_child geometry '{child_geom}' unknown"


if __name__ == "__main__":
    test_walker2_skeleton_structure()
    test_hatshirt_skeleton_structure_and_depth()
    test_no_orphan_or_cyclic_bones()
    test_attachments_reference_real_bones_and_geometry()
    print("test_skeleton.py: all tests passed")
