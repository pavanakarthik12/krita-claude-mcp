"""
Minimal heading/facing data representation - Phase 1 scope only.

This module exists to give "which way the character faces" a real,
named, testable data type BEFORE any Action (walk, turn, ...) is built on
top of it - directly in response to the 120-frame walking experiment's
diagnosed failure, where the apparent walking direction was an accidental
side effect of rotation sign conventions and per-limb phase offsets
buried in walker2_full_animation.py, with no explicit "which way is
forward" concept anywhere.

Deliberately NOT wired into TransformEvaluator or any bone transform in
this phase (per the instructions: heading must not be mixed into
individual limb transformations). It is pure data + a couple of
world-space helper functions, ready for a future root-bone rotation
delta to consume once the Action system exists.
"""
import math

HEADING_RIGHT = 0.0    # facing screen-right (+x), matches this trace's rest_facing
HEADING_LEFT = 180.0   # facing screen-left (-x)


def world_forward_vector(heading_deg):
    """Unit vector in canvas/world space that this heading faces.
    0 deg = [1, 0] (screen-right), 180 deg = [-1, 0] (screen-left)."""
    a = math.radians(heading_deg)
    return [math.cos(a), math.sin(a)]


def normalize_heading(heading_deg):
    """Wrap to [0, 360)."""
    return heading_deg % 360.0


def is_mirrored(heading_deg, rest_facing_deg=HEADING_RIGHT):
    """Whether this heading faces the opposite way from the character's
    rest-pose facing direction - the flag a future walk Action would use
    to decide whether to mirror its limb-swing signs, rather than baking
    a fixed swing direction into the animation formula as before."""
    diff = abs(normalize_heading(heading_deg) - normalize_heading(rest_facing_deg))
    diff = min(diff, 360.0 - diff)
    return diff > 90.0
