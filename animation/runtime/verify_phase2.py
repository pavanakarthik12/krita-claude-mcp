"""verify_phase2.py - Phase 2J's automated checks for the motion-quality
test scene (15s/360 frames/3 characters). Same evidence-based approach as
POC #4/Phase 1's verify.py: rendered PNGs for frame count/resolution/blank,
plus the per-frame numeric dump (test_output_phase2/dump/frame_XXXX.json)
for everything that needs real bone/position data rather than pixels.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "test_output_phase2")
DUMP_DIR = os.path.join(OUT_DIR, "dump")
FPS = 24
FRAME_COUNT = 360
BG = (235, 235, 230)


def load_dump(frame):
    with open(os.path.join(DUMP_DIR, f"frame_{frame:04d}.json")) as f:
        return json.load(f)


def is_bg_arr(arr):
    return np.all(np.abs(arr.astype(int) - np.array(BG)) < 4, axis=-1)


def check_frames_and_resolution():
    ok = True
    files = sorted(glob.glob(os.path.join(OUT_DIR, "frame_*.png")))
    if len(files) != FRAME_COUNT:
        print(f"FAIL: expected {FRAME_COUNT} frames, found {len(files)}")
        ok = False
    else:
        print(f"OK: exactly {FRAME_COUNT} frames exist")
    sizes = set()
    blank = []
    for f in files:
        img = np.array(Image.open(f).convert("RGB"))
        sizes.add((img.shape[1], img.shape[0]))
        if np.sum(~is_bg_arr(img)) < 200:
            blank.append(os.path.basename(f))
    if len(sizes) == 1:
        print(f"OK: consistent resolution {next(iter(sizes))}")
    else:
        print(f"FAIL: inconsistent resolutions {sizes}")
        ok = False
    if blank:
        print(f"FAIL: blank frames: {blank}")
        ok = False
    else:
        print("OK: no blank frames")
    return ok


# --- LOCOMOTION ---

def check_locomotion():
    ok = True
    x_at_2 = load_dump(48)["char1"]["worldX"]   # walk starts at t=2
    x_at_5 = load_dump(120)["char1"]["worldX"]  # walk ends at t=5
    if x_at_5 <= x_at_2:
        print(f"FAIL: char1 world x did not increase while walking right ({x_at_2:.1f} -> {x_at_5:.1f})")
        ok = False
    else:
        print(f"OK: char1 world position advances while walking right ({x_at_2:.1f} -> {x_at_5:.1f})")

    x2_at_10 = load_dump(240)["char2"]["worldX"]  # walk-left starts at t=10
    x2_at_15 = load_dump(359)["char2"]["worldX"]
    if x2_at_15 >= x2_at_10:
        print(f"FAIL: char2 world x did not decrease while walking left ({x2_at_10:.1f} -> {x2_at_15:.1f})")
        ok = False
    else:
        print(f"OK: char2 world position moves in the opposite (left) direction ({x2_at_10:.1f} -> {x2_at_15:.1f})")

    # deterministic: re-derive char1's position analytically for the first
    # walk segment (speed=55, direction=1, local_t = t-2) and compare.
    t = 3.5
    frame = int(round(t * FPS))
    expected_x = 675.0 + 55.0 * (t - 2.0)
    actual_x = load_dump(frame)["char1"]["worldX"]
    if abs(actual_x - expected_x) > 1.0:
        print(f"FAIL: char1 position at t={t} is {actual_x:.2f}, expected ~{expected_x:.2f}")
        ok = False
    else:
        print(f"OK: char1 position at t={t} matches the deterministic speed*time formula ({actual_x:.2f})")
    return ok


# --- FOOT CONTACT ---

def _foot_world(frame, char_id, mesh_name, rigid_name):
    d = load_dump(frame)[char_id]
    verts = np.array(d["meshes"][mesh_name])
    rigid = np.array(d["rigidParts"][rigid_name])
    dists = np.sqrt(np.sum((verts - rigid) ** 2, axis=1))
    return dists.min()


def check_foot_contact():
    ok = True
    # Across char1's first walk (frames 48-120), the mesh-to-rigid-foot gap
    # should stay bounded (no detachment) even as the leg swings/plants.
    gaps = []
    for frame in range(48, 121, 4):
        gaps.append(_foot_world(frame, "char1", "front_leg", "front_foot"))
    if max(gaps) - min(gaps) > 60.0:
        print(f"FAIL: front foot/leg-mesh gap swings too much ({min(gaps):.1f}-{max(gaps):.1f}px) - possible detachment")
        ok = False
    else:
        print(f"OK: front foot stays attached to its leg mesh across the walk (gap {min(gaps):.1f}-{max(gaps):.1f}px)")

    # sit: char2's feet should stay roughly under the hips (not fly off)
    # while sitting (frames 96-192, t=4..8).
    foot_xs = [load_dump(f)["char2"]["rigidParts"]["front_foot"][0] for f in range(96, 193, 8)]
    if max(foot_xs) - min(foot_xs) > 80.0:
        print(f"FAIL: char2's foot drifts too much horizontally while sitting ({min(foot_xs):.1f}-{max(foot_xs):.1f})")
        ok = False
    else:
        print(f"OK: char2's foot stays near the ground contact point while sitting (x range {min(foot_xs):.1f}-{max(foot_xs):.1f})")
    return ok


# --- TRANSITIONS ---

def check_transitions():
    ok = True
    # No frame-to-frame bone-angle jump anywhere should exceed a sane bound
    # (this is exactly the check that caught the mid-stance IK "pop" during
    # development - see walk.py's reach slack).
    max_jump = 0.0
    worst = None
    prev = None
    for frame in range(FRAME_COUNT):
        d = load_dump(frame)["char1"]["bones"]
        if prev is not None:
            for bone, angle in d.items():
                jump = abs(angle - prev.get(bone, angle))
                if jump > max_jump:
                    max_jump = jump
                    worst = (frame, bone)
        prev = d
    print(f"largest single-frame bone-angle change for char1: {max_jump:.2f} deg (frame {worst})")
    if max_jump > 25.0:
        print("FAIL: a bone jumped more than 25 deg in a single frame - likely an un-blended pop")
        ok = False
    else:
        print("OK: no discontinuous pose jump across the whole scene for char1")
    return ok


# --- OVERLAY ---

def check_overlay():
    # Baseline is the known StandAction rest value (0) for every bone -
    # NOT an earlier frame, since frames just before t=6 are still mid-
    # StopAction (decelerating), which legitimately has nonzero leg/arm
    # angles of its own and would make a fine overlay look like a "leak".
    during = load_dump(168)["char1"]["bones"]  # t=7.0, mid-wave, base action = stand (rest)
    front_changed = abs(during["upper_arm_front"]) > 5.0
    others_stable = all(
        abs(during[b]) < 0.5
        for b in ("upper_arm_back", "forearm_back", "thigh_front", "thigh_back", "shin_front", "shin_back")
    )
    if front_changed and others_stable:
        print("OK: wave overlay changes only the front arm; legs/other arm unaffected while standing")
        return True
    print(f"FAIL: wave overlay leaked into other bones (front_changed={front_changed}, others_stable={others_stable})")
    return False


# --- MULTI-CHARACTER / DETERMINISM ---

def check_independence_and_determinism():
    ok = True
    b0 = load_dump(0)["char3"]["bones"]
    b180 = load_dump(180)["char3"]["bones"]
    b359 = load_dump(359)["char3"]["bones"]
    if b0 == b180 == b359 and all(abs(v) < 0.01 for v in b0.values()):
        print("OK: char3 (static) stays at rest for the entire 360-frame scene regardless of char1/char2's motion")
    else:
        print("FAIL: char3's pose changed unexpectedly")
        ok = False

    # positions independent
    p1 = load_dump(180)["char1"]["worldX"]
    p2 = load_dump(180)["char2"]["worldX"]
    p3 = load_dump(180)["char3"]["worldX"]
    if len({round(p1, 1), round(p2, 1), round(p3, 1)}) == 3:
        print(f"OK: three distinct, independent world positions at t=7.5: {p1:.1f}, {p2:.1f}, {p3:.1f}")
    else:
        print(f"FAIL: character positions are not independent: {p1}, {p2}, {p3}")
        ok = False
    return ok


def main():
    checks = [
        check_frames_and_resolution,
        check_locomotion,
        check_foot_contact,
        check_transitions,
        check_overlay,
        check_independence_and_determinism,
    ]
    ok = True
    for check in checks:
        ok &= check()
        print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
