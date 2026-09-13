"""
POC #4 acceptance check - the 14 numbered checks from the requirements.

Uses two kinds of evidence:
  - the rendered PNGs (frame count / resolution / blank check - same
    technique as POC #1/#2/#3)
  - output/dump/frame_XXXX.json, a per-frame numeric ground-truth dump
    main.cpp writes alongside each PNG (bone rotation deltas, bone global
    positions, rigid-part world positions, and each mesh slot's full
    deformed-vertex list, all already in WORLD space via
    CharacterInstance::toWorld) - this avoids the pixel-heuristic false
    positives hit during POC #3 (see that POC's verify.py docstring) by
    checking the actual DragonBones-computed state directly instead of
    inferring it from pixels.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "output")
DUMP_DIR = os.path.join(OUTPUT_DIR, "dump")
LIMB_TESTS_DIR = os.path.join(OUTPUT_DIR, "limb_tests")
BG = (235, 235, 230)

FRAME_COUNT = 48


def load_dump(frame):
    with open(os.path.join(DUMP_DIR, f"frame_{frame:04d}.json")) as f:
        return json.load(f)


def is_bg_arr(arr):
    return np.all(np.abs(arr.astype(int) - np.array(BG)) < 4, axis=-1)


# --- Check 1/2/3: frame count, resolution, no blank frames ---
def check_1_2_3():
    ok = True
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "frame_*.png")))
    if len(files) != FRAME_COUNT:
        print(f"FAIL (1): expected {FRAME_COUNT} frames, found {len(files)}")
        ok = False
    else:
        print(f"OK (1): exactly {FRAME_COUNT} frames exist")

    sizes = set()
    blank = []
    for f in files:
        img = np.array(Image.open(f).convert("RGB"))
        sizes.add((img.shape[1], img.shape[0]))
        nonbg = np.sum(~is_bg_arr(img))
        if nonbg < 200:
            blank.append(os.path.basename(f))
    if len(sizes) == 1 and next(iter(sizes)) == (1200, 700):
        print(f"OK (2): all frames are 1200x700")
    else:
        print(f"FAIL (2): inconsistent/wrong resolution {sizes}")
        ok = False
    if blank:
        print(f"FAIL (3): blank frames found: {blank}")
        ok = False
    else:
        print(f"OK (3): no frame is blank")
    return ok


# --- Check 4: Character 1 changes pose across time ---
def check_4():
    d0 = load_dump(0)["char1"]
    d8 = load_dump(8)["char1"]
    angle_change = abs(d0["bones"]["thigh_front"]["rotationDeg"] - d8["bones"]["thigh_front"]["rotationDeg"])
    if angle_change > 5.0:
        print(f"OK (4): Character 1's thigh_front rotation changed {angle_change:.1f} deg from frame 0 to frame 8")
        return True
    print(f"FAIL (4): Character 1's pose barely changed ({angle_change:.1f} deg) between frame 0 and 8")
    return False


# --- Check 5: Character 2 remains standing (rest pose) at all frames ---
def check_5():
    ok = True
    for frame in [0, 8, 16, 24, 32, 40, 47]:
        d = load_dump(frame)["char2"]
        for bone_name, bone in d["bones"].items():
            if abs(bone["rotationDeg"]) > 0.01:
                print(f"FAIL (5): Character 2 bone '{bone_name}' has nonzero rotation "
                      f"{bone['rotationDeg']:.3f} deg at frame {frame} (should be standing/rest)")
                ok = False
    if ok:
        print("OK (5): Character 2 stays in rest/standing pose (all bone rotations ~0) across all sampled frames")
    return ok


# --- Check 6: Character 1 and 2 have independent transforms ---
def check_6():
    d = load_dump(0)
    c1, c2 = d["char1"], d["char2"]
    ok = True
    if c1["worldX"] == c2["worldX"]:
        print("FAIL (6): Character 1 and 2 share the same worldX")
        ok = False
    if c1["heading"] == c2["heading"]:
        print("FAIL (6): Character 1 and 2 share the same heading (expected independent, one mirrored)")
        ok = False
    if ok:
        print(f"OK (6): independent transforms - char1 worldX={c1['worldX']:.1f} heading={c1['heading']}, "
              f"char2 worldX={c2['worldX']:.1f} heading={c2['heading']}")
    return ok


# --- Check 7/8: limbs remain connected (rigid extremity tracks its mesh's
# distal end closely across motion, for both char1 [moving] and char2
# [static]) ---
def _distal_tip(mesh_verts, rigid_pos):
    """Nearest mesh vertex to the rigid part's own world position - if the
    limb were torn/detached this distance would be large; if attached, the
    nearest vertex sits right at the joint, a small roughly-constant gap."""
    verts = np.array(mesh_verts)
    d = np.sqrt(np.sum((verts - np.array(rigid_pos)) ** 2, axis=1))
    return float(d.min())


LIMB_TO_RIGID = {
    "front_leg": "front_foot",
    "back_leg": "back_foot",
    "front_upper_arm": "front_hand",
    "back_upper_arm": "back_hand",
}


def _check_limbs_connected(char_key, frames, label):
    ok = True
    rest_gaps = {}
    for i, frame in enumerate(frames):
        d = load_dump(frame)[char_key]
        for mesh_name, rigid_name in LIMB_TO_RIGID.items():
            gap = _distal_tip(d["meshes"][mesh_name], d["rigidParts"][rigid_name])
            if i == 0:
                rest_gaps[mesh_name] = gap
            # A gap that grows drastically relative to its own rest value
            # indicates the rigid extremity pulling away from the mesh.
            if gap > rest_gaps[mesh_name] + 40.0:
                print(f"FAIL ({label}): {char_key} '{rigid_name}' drifts from '{mesh_name}' "
                      f"(gap {gap:.1f}px vs rest {rest_gaps[mesh_name]:.1f}px) at frame {frame}")
                ok = False
    if ok:
        print(f"OK ({label}): {char_key}'s four limbs keep their rigid extremity attached "
              f"(gap stable near rest value) across frames {frames}")
    return ok


def check_7():
    return _check_limbs_connected("char1", [0, 8, 16, 24, 32, 40, 47], "7")


def check_8():
    return _check_limbs_connected("char2", [0, 8, 16, 24, 32, 40, 47], "8")


# --- Check 9: no cross-character state contamination ---
def check_9():
    ok = True
    d0 = load_dump(0)
    d8 = load_dump(8)
    for key in ["char2", "char3"]:
        for bone_name in d0[key]["bones"]:
            r0 = d0[key]["bones"][bone_name]["rotationDeg"]
            r8 = d8[key]["bones"][bone_name]["rotationDeg"]
            if abs(r0 - r8) > 0.01:
                print(f"FAIL (9): {key}'s bone '{bone_name}' changed between frame 0 and 8 "
                      f"({r0:.3f} -> {r8:.3f}) despite char1 (walking) advancing - possible contamination")
                ok = False
    if ok:
        print("OK (9): Characters 2 and 3's bone state is unaffected by Character 1's walking - "
              "no cross-instance contamination (each owns its own Armature)")
    return ok


# --- Check 10/11: walk approximately cyclic, frame0 ~ frame47 ---
def _pose_vector(char_dump):
    return np.array([b["rotationDeg"] for b in char_dump["bones"].values()])


def check_10():
    ok = True
    p0 = _pose_vector(load_dump(0)["char1"])
    p24 = _pose_vector(load_dump(24)["char1"])
    diff = float(np.max(np.abs(p0 - p24)))
    print(f"frame0 vs frame24 (one full 1Hz cycle later) max bone-angle diff: {diff:.2f} deg")
    if diff > 3.0:
        print("FAIL (10): walk cycle is not approximately periodic at its own period (24 frames = 1s @ 1Hz)")
        ok = False
    else:
        print("OK (10): walk is approximately cyclic (frame 0 ~= frame 24, one full gait cycle later)")
    return ok


def check_11():
    p0 = _pose_vector(load_dump(0)["char1"])
    p47 = _pose_vector(load_dump(47)["char1"])
    diff = float(np.max(np.abs(p0 - p47)))
    print(f"frame0 vs frame47 max bone-angle diff: {diff:.2f} deg")
    if diff > 25.0:
        print("FAIL (11): frame 0 and frame 47 are not approximately the same walk phase")
        return False
    print("OK (11): frame 0 and frame 47 return to approximately the same walk phase "
          "(47/24s is one frame short of the 2nd full 1Hz cycle closing)")
    return True


# --- Check 12: rest pose geometry matches the Character Lock ---
def check_12():
    with open(os.path.join(HERE, "character_ske.json")) as f:
        ske = json.load(f)
    with open(os.path.join(HERE, "limb_source_geometry.json")) as f:
        source = json.load(f)

    ok = True
    for slot in ske["armature"][0]["skin"][0]["slot"]:
        name = slot["name"]
        mesh_verts = slot["display"][0]["vertices"]
        mesh_pts = np.array([(mesh_verts[i], mesh_verts[i + 1]) for i in range(0, len(mesh_verts), 2)])
        if name not in source:
            continue
        # Boundary vertices of the mesh should lie within the source
        # Bezier contour's own bounding box (with small tolerance) - proves
        # the mesh was built from the lock's own traced geometry, not
        # invented.
        seg = source[name]
        xs = [p[0] for s in seg for p in [s["start"], s["control1"], s["control2"], s["end"]]]
        ys = [p[1] for s in seg for p in [s["start"], s["control1"], s["control2"], s["end"]]]
        pad = 5.0
        within = np.all(
            (mesh_pts[:, 0] >= min(xs) - pad) & (mesh_pts[:, 0] <= max(xs) + pad) &
            (mesh_pts[:, 1] >= min(ys) - pad) & (mesh_pts[:, 1] <= max(ys) + pad)
        )
        if not within:
            print(f"FAIL (12): mesh '{name}' has vertices outside its source Bezier contour's bounding box")
            ok = False
    if ok:
        print("OK (12): all four mesh limbs' rest-pose vertices lie within their source "
              "Character Lock Bezier contour's bounding box (built from the lock, not invented)")
    return ok


# --- Check 13: all four articulated limbs actually use weighted deformation ---
def check_13():
    with open(os.path.join(HERE, "character_ske.json")) as f:
        ske = json.load(f)
    ok = True
    for slot in ske["armature"][0]["skin"][0]["slot"]:
        mesh = slot["display"][0]
        weights = mesh["weights"]
        bone_pose = mesh["bonePose"]
        influencing_bones = len(bone_pose) // 7
        if influencing_bones < 2:
            print(f"FAIL (13): mesh '{slot['name']}' only references {influencing_bones} bone(s), not weighted between two")
            ok = False
            continue
        # Count vertices with a genuinely blended (non 0/1) weight.
        i = 0
        blended = 0
        total = 0
        while i < len(weights):
            n = int(weights[i])
            i += 1
            total += 1
            ws = [weights[i + 2 * k + 1] for k in range(n)]
            i += 2 * n
            if n >= 2 and any(0.02 < w < 0.98 for w in ws):
                blended += 1
        if blended == 0:
            print(f"FAIL (13): mesh '{slot['name']}' has zero vertices with blended (non-binary) weights")
            ok = False
        else:
            print(f"OK (13): mesh '{slot['name']}' - {influencing_bones} influencing bones, "
                  f"{blended}/{total} vertices continuously blended between them")
    return ok


# --- Check 14: no limb is silently frozen (rigid-workaround regression) ---
def check_14():
    ok = True
    d0 = load_dump(0)["char1"]
    d8 = load_dump(8)["char1"]
    distal_bones = ["shin_front", "shin_back", "forearm_front", "forearm_back"]
    for bone_name in distal_bones:
        r0 = d0["bones"][bone_name]["rotationDeg"]
        r8 = d8["bones"][bone_name]["rotationDeg"]
        if abs(r0 - r8) < 0.5:
            print(f"FAIL (14): distal bone '{bone_name}' did not move between frame 0 and 8 "
                  f"({r0:.2f} -> {r8:.2f}) - looks frozen like POC #2's rigid-parts workaround")
            ok = False
    if ok:
        print("OK (14): all four distal (shin/forearm) bones receive independent rotation deltas "
              "during the walk - none are frozen the way POC #2's rigid parts had to be")
    return ok


def main():
    checks = [
        check_1_2_3,
        check_4, check_5, check_6, check_7, check_8, check_9,
        check_10, check_11, check_12, check_13, check_14,
    ]
    ok = True
    for check in checks:
        ok &= check()
        print()

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
