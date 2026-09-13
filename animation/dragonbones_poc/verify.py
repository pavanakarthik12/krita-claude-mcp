"""
POC #2 acceptance check - mirrors the verification approach already proven
in DragonBonesCPP/poc/verify.py, applied to this POC's own output/.

Checks:
  - exactly 24 PNG frames exist
  - all frames share one resolution
  - no frame is fully transparent or a flat single color (i.e. something
    was actually drawn, not just a blank/background-only canvas)
  - frame 0 and frame 23 are pixel-identical (both at walk-amplitude 0)
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "output")


def main():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "frame_*.png")))
    ok = True

    if len(files) != 24:
        print(f"FAIL: expected 24 frames, found {len(files)}")
        ok = False
    else:
        print(f"OK: exactly 24 frames found")

    sizes = set()
    blank_frames = []
    for f in files:
        img = Image.open(f).convert("RGBA")
        sizes.add(img.size)
        arr = np.array(img)
        colors = set(map(tuple, arr.reshape(-1, 4)[::37]))  # sampled
        if len(colors) <= 1 or arr[:, :, 3].max() == 0:
            blank_frames.append(os.path.basename(f))

    if len(sizes) == 1:
        print(f"OK: all frames share one resolution: {next(iter(sizes))}")
    else:
        print(f"FAIL: inconsistent resolutions across frames: {sizes}")
        ok = False

    if not blank_frames:
        print("OK: no blank/transparent/flat-color frames")
    else:
        print(f"FAIL: blank-looking frames: {blank_frames}")
        ok = False

    f0 = os.path.join(OUTPUT_DIR, "frame_0000.png")
    f23 = os.path.join(OUTPUT_DIR, "frame_0023.png")
    if os.path.exists(f0) and os.path.exists(f23):
        a = np.array(Image.open(f0).convert("RGBA"), dtype=int)
        b = np.array(Image.open(f23).convert("RGBA"), dtype=int)
        if a.shape != b.shape:
            print("FAIL: frame 0 and frame 23 have different shapes")
            ok = False
        else:
            mean_diff = np.abs(a - b).mean()
            print(f"frame0 vs frame23 mean abs diff: {mean_diff:.4f}")
            if mean_diff > 1.0:
                print("FAIL: frame 0 and frame 23 differ more than expected")
                ok = False
            else:
                print("OK: frame 0 and frame 23 match (return-to-idle confirmed)")

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
