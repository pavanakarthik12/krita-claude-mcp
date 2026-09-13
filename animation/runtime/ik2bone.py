"""Standard closed-form 2-bone (law-of-cosines) analytic IK.

Phase 2B originally tried to wire DragonBones' OWN native IK constraint
system (see build_ik_skeleton.py / git history) - it was abandoned after
empirical testing (ik_probe.py) showed it produces a contorted leg on this
asset, because DragonBones' IKConstraint::_computeB assumes standard
rotation INHERITANCE down the bone chain, while this rig's leg bones use
"inheritRotation: false" (POC #2's deliberate convention letting pose code
write pure rotation deltas without hand-composing FK). Reworking the whole
skeleton's rotation convention to satisfy the native constraint was out of
scope for this phase.

This module is the documented fallback: the textbook closed-form two-bone
IK formula (not a general/iterative solver), producing plain rotation
DELTAS that flow through the exact same, unmodified bone-rotation pipeline
every other pose value already uses - no new DragonBones data format, no
C++ changes.
"""
import math
from dataclasses import dataclass


@dataclass
class LegGeometry:
    hip_x: float
    hip_y: float
    upper_length: float
    lower_length: float
    rest_angle_rad: float  # world angle (rig-local space) of the straight rest leg
    bend_sign: float  # +1 or -1, selects which way the knee bends


def solve_2bone_ik(target_x: float, target_y: float, geom: LegGeometry):
    """Returns (upper_rotation_deg_delta, lower_rotation_deg_delta) - the
    rotation DELTA from each bone's own rest orientation needed so the
    lower bone's tip reaches (target_x, target_y). Degenerates gracefully
    (clamped) for unreachable targets instead of raising."""
    dx = target_x - geom.hip_x
    dy = target_y - geom.hip_y
    dist = math.hypot(dx, dy)

    l1, l2 = geom.upper_length, geom.lower_length
    eps = 1e-3
    dist = max(abs(l1 - l2) + eps, min(l1 + l2 - eps, dist))
    dist = max(dist, eps)

    target_angle = math.atan2(dy, dx)

    cos_alpha = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
    alpha = math.acos(max(-1.0, min(1.0, cos_alpha)))
    upper_angle = target_angle - geom.bend_sign * alpha

    cos_beta = (l1 * l1 + l2 * l2 - dist * dist) / (2.0 * l1 * l2)
    beta = math.acos(max(-1.0, min(1.0, cos_beta)))
    lower_angle = upper_angle + geom.bend_sign * (math.pi - beta)

    upper_delta_deg = math.degrees(upper_angle) - math.degrees(geom.rest_angle_rad)
    lower_delta_deg = math.degrees(lower_angle) - math.degrees(geom.rest_angle_rad)
    return upper_delta_deg, lower_delta_deg
