# POC #2 — Character Lock → DragonBones Asset → Procedural Pose → Rendered Frames

This directory proves one specific thing, using the real `walker2` Character
Lock and the already-proven DragonBones runtime POC's architecture
(`../../DragonBonesCPP/poc`), unmodified:

```
character_lock_walker2_v2.json (unmodified, authoritative source)
    -> DragonBones skeleton JSON (bone hierarchy: name/parent/rest pivot/
       rest orientation/length, converted, not hand-typed)
    -> rigid rasterized PNG per traced Bézier component (no mesh deformation)
    -> DragonBones C++ core (unmodified) driving bone->offset per frame
    -> deterministic 24-frame walk cycle (idle -> walk -> return), 24 FPS
    -> SFML off-screen rendering
    -> 24 PNG frames on disk
```

Nothing outside this directory was modified: not the Character Lock files
in `animation/data/`, not `animation/*.py` (only imported, read-only), not
the MCP server/plugin, and not the DragonBones runtime in
`../../DragonBonesCPP` (compiled from its existing location, `src/PocRuntime.h`
is a verbatim copy of that POC's own glue code).

## Files

```
dragonbones_poc/
  convert_lock_to_dragonbones.py   Character Lock -> character_ske.json + parts/*.png + parts_manifest.json
  character_ske.json               generated DragonBones skeleton (11 bones)
  parts_manifest.json              generated: which PNG binds to which bone, and its pivot offset
  parts/*.png                      10 rasterized rigid components
  src/main.cpp                     procedural pose + deterministic frame loop + SFML render + PNG export
  src/PocRuntime.h                 verbatim copy of the proven POC's headless DragonBones glue (unmodified)
  build.sh                         builds against ../../DragonBonesCPP/DragonBones/src (unmodified, external)
  verify.py                        acceptance check against output/
  output/frame_0000.png .. frame_0023.png
```

## Character Lock used

`animation/data/character_lock_walker2_v2.json` — loaded via the existing,
unmodified `CharacterLockModel` / `Bone` / `Attachment` classes
(`animation/character_model.py`, `animation/bone.py`). Checksum and skeleton
validated (`model.checksum_valid()`, `model.validate_skeleton()`) before any
conversion runs; the script aborts if either fails.

## Conversion process

1. Load the lock read-only via `CharacterLockModel.from_file(...)`.
2. For every bone in `model.skeleton` (11 bones, arbitrary-depth walk via
   `root_bones()`/`children_of()` — nothing walker2-specific assumed), emit
   a DragonBones `bone` entry:
   - `name`, `parent`, `length` copied directly.
   - Rest **rotation** (`skX`/`skY`) = the bone's accumulated
     `rest_orientation_deg` chain (parent rotation + this bone's own,
     mirroring `transform_evaluator.py`'s own additive formula, reused not
     reimplemented).
   - Rest **position** (`transform.x/y`) = the child's raw `rest_pivot`
     expressed in the parent's rest-oriented local frame (the parent-child
     pivot difference, rotated back by `-parent_rotation`) — **using each
     bone's own raw `rest_pivot`, not
     `TransformEvaluator.bone_world()`'s recomposed pivot**. This was a real
     bug caught before rendering: `bone_world()`'s formula is correct for
     composing a *posed* chain, but does not reproduce a bone's own raw
     `rest_pivot` at rest when an ancestor has a non-zero
     `rest_orientation_deg` (confirmed numerically for `shin_back`: ~50px
     off). Verified by direct computation that using the raw pivot,
     rotated by the parent's accumulated rest rotation, round-trips back to
     the bone's exact original `rest_pivot` once DragonBones recomposes the
     hierarchy at rest.
   - Every non-root bone gets `"inheritRotation": false`, matching the
     already-proven POC's pattern: at animation time only the pose *delta*
     is written to `bone->offset.rotation`, never a hand-composed absolute
     angle.
3. For every entry in `model.components_geometry` (10 components), flatten
   its cubic-Bézier segments (as stored, unchanged) into a polygon and
   rasterize it with Pillow to a tightly-cropped, transparent-background
   PNG. Each component is bound to one bone (`COMPONENT_TO_BONE`), following
   the lock's own `attachments` data: the attachment's proximal bone for the
   main limb contour, the distal bone for its `rigid_children` (hand/foot).

## DragonBones skeleton mapping

| Character Lock bone | DragonBones parent | length | rest skX/skY (deg) |
|---|---|---|---|
| root | (none) | — | — |
| torso | root | 148.05 | 0.0 |
| head | torso | 395.15 | 0.0 |
| upper_arm_front | torso | 161.16 | 34.22 |
| forearm_front | upper_arm_front | 136.05 | 34.22 |
| upper_arm_back | torso | 152.89 | -25.41 |
| forearm_back | upper_arm_back | 122.34 | -25.41 |
| thigh_front | torso | 147.82 | 31.28 |
| shin_front | thigh_front | 147.78 | 31.28 |
| thigh_back | torso | 151.75 | -17.44 |
| shin_back | thigh_back | 180.38 | -17.44 |

All 11 bones, names, parents, lengths and rest orientations are exactly the
lock's own values (rotations chained additively, positions taken directly
from `rest_pivot`) — nothing invented.

## Rasterized components (10)

`head`, `torso`, `front_upper_arm`, `front_hand`, `back_upper_arm`,
`back_hand`, `front_leg`, `front_foot`, `back_leg`, `back_foot` — one PNG
each, flat-colored fills of the traced contour (color is a POC rendering
choice only, not lock data), bound respectively to `head`, `torso`,
`upper_arm_front`, `forearm_front`, `upper_arm_back`, `forearm_back`,
`thigh_front`, `shin_front`, `thigh_back`, `shin_back`.

## Render method

`src/main.cpp`, built via `build.sh` against the unmodified DragonBones C++
core at `../../DragonBonesCPP/DragonBones/src` (compiled from its existing
location, nothing copied or modified) plus SFML for off-screen rendering —
the exact same technique as the proven POC: read `bone->global`/`offset`
after `Armature::advanceTime()`, draw ourselves (here: `sf::Sprite` per
part, origin set to the part's pivot, instead of primitive rectangles).

## Animation

24 frames @ 24 FPS, `t = frame / 24.0`:
- frames 0-5: idle (amplitude 0)
- frames 6-17: walk cycle (amplitude 1, sine gait, opposite-phase legs and
  contralateral arm swing)
- frames 18-23: smoothstep ease back to amplitude 0, landing exactly at 0
  on frame 23

Only the **proximal** bones of each limb (`thigh_front/back`,
`upper_arm_front/back`) are driven with a pose delta — see "visual problems"
below for why the distal bones (`shin_*`, `forearm_*`) are deliberately kept
at delta 0.

## Verification results (`python3 verify.py`)

```
OK: exactly 24 frames found
OK: all frames share one resolution: (993, 1510)
OK: no blank/transparent/flat-color frames
frame0 vs frame23 mean abs diff: 0.0000
OK: frame 0 and frame 23 match (return-to-idle confirmed)

PASS
```
Visual inspection (frames 0, 6, 9, 12, 15, 17, 20, 23) confirmed: head,
torso, both arms (with hands), both legs (with feet) remain attached in
every frame; proportions stay consistent; the character reads as the same
recognizable stick figure throughout.

## Visual problems found (and the one tiny fix applied)

**Found**: `front_leg`/`back_leg` and `front_upper_arm`/`back_upper_arm` are
each a *single* rigid image spanning the lock's original two-joint
(`soft_skin_2joint`) contour (hip-to-ankle / shoulder-to-wrist in one
traced shape). Their `rigid_children` (foot/hand) are bound to the
*distal* bone (`shin_*`/`forearm_*`), a **different** bone than the limb
image (bound to the *proximal* bone). Animating the distal bone
independently (an initial version of `main.cpp` did) swings the foot/hand
away from the limb image, which cannot itself bend — producing a clearly
detached foot/hand at the ankle/wrist (reproduced and screenshotted during
this POC, frame 12 of the first build).

**Fix applied** (in scope — not mesh deformation, just which bones get an
animated delta): the distal bones' `offset.rotation` is kept at 0 every
frame; only the proximal bone swings the whole rigid limb (image + its
attached hand/foot) as one unit. This is the correct rigid-parts treatment
of geometry that was traced as one continuous contour, and it eliminated
the detachment (confirmed by re-rendering and re-inspecting).

**Remaining, undocumented-as-a-problem cosmetic note**: with no knee/elbow
bend, the legs/arms swing as straight rigid rods from the hip/shoulder —
visually plausible for this POC's "does it survive animation" question, but
not an anatomically bending walk. This is the expected, disclosed
consequence of "no weighted mesh deformation yet," not a defect.

A minor z-order artifact is visible in some walk frames (e.g. frame 9): the
back arm's rigid image slightly overlaps the torso's silhouette edge near
the shoulder pivot, a cosmetic layering/pivot-precision issue, not an
attachment failure.

## Whether the Character Lock survived the conversion

**Yes.** All 11 bones (name, parent, length, rest orientation) and all 10
traced components made it through unchanged in substance; the resulting
character is recognizable, fully attached, and completes a 24-frame
idle→walk→idle cycle returning exactly to its start pose, satisfying this
POC's stated goal.

## What POC #3 needs

1. **Weighted mesh deformation** for the four two-joint limbs (replacing
   the "freeze the distal joint" workaround here) — either a DragonBones
   `mesh` display with per-vertex bone weights, or reuse of
   `articulation_lib.transform_two_joint`'s existing weight-blend directly
   as a pre-render deformation step before rasterizing each frame.
2. **Texture atlas packing** of the 10 (or more, once other locks are
   added) part PNGs into one atlas + `_tex.json`, if moving to a real
   DragonBones-slot-based renderer instead of this POC's "read bone
   transforms, draw sprites ourselves" approach.
3. A z-order/pivot pass to remove the minor shoulder overlap noted above.
4. Extending `COMPONENT_TO_BONE` / the conversion script to be
   attachment-driven (read `strategy`/`rigid_children` generically) instead
   of a hand-written per-component table, so a second lock (e.g.
   `character_lock_hatshirt_v2.json`) converts without new code.
