"""
Two-joint articulation via smooth per-point rotation blending.

Does NOT cut, reshape, or regenerate any locked geometry. Every point in a
limb's locked Bezier segments keeps its identity; only a rotation angle is
computed per point, continuously varying from 0 (at the pivot) to 1 (at the
tip), so there is no seam/gap introduced at the "joint" - see report for why
a hard cut of a closed tapered contour cannot stay seamless at two points.

At theta2 = 0 this is IDENTICAL to the existing single-pivot rigid rotation
(verified in verify_lock_integrity3.py) - this is additive, not a
replacement of the working rotation system.
"""
import math


def rotate_pt(p, pivot, angle_deg):
    if not angle_deg:
        return [p[0], p[1]]
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = p[0] - pivot[0], p[1] - pivot[1]
    return [pivot[0] + dx * ca - dy * sa, pivot[1] + dx * sa + dy * ca]


def axis_weight(p, pivot, tip):
    """0 at pivot, 1 at tip, clamped - projection onto the pivot->tip axis.
    Purely a function of the point's LOCKED rest position; never alters it."""
    ax, ay = tip[0] - pivot[0], tip[1] - pivot[1]
    axis_len_sq = ax * ax + ay * ay
    if axis_len_sq < 1e-9:
        return 0.0
    t = ((p[0] - pivot[0]) * ax + (p[1] - pivot[1]) * ay) / axis_len_sq
    return max(0.0, min(1.0, t))


def precompute_weights(locked_segs, pivot, tip):
    """One weight per (segment_index, key) for a limb's locked geometry."""
    weights = []
    for seg in locked_segs:
        w = {}
        for k in ("start", "control1", "control2", "end"):
            w[k] = axis_weight(seg[k], pivot, tip)
        weights.append(w)
    return weights


def transform_two_joint(locked_segs, weights, pivot, joint_rest, theta1, theta2, bob):
    """Stage 1: rotate everything by theta1 around pivot (== existing rigid
    behavior, unchanged). Stage 2: rotate each point an EXTRA weight*theta2
    around the knee/elbow point (joint_rest) AFTER stage 1 has moved it.
    Since every point's stage-2 rotation is centered on that one shared,
    consistently-computed point, continuity is exact by construction - no
    cut, no gap, regardless of weight."""
    joint_pivot_after_stage1 = rotate_pt(joint_rest, pivot, theta1)
    out = []
    for seg, w in zip(locked_segs, weights):
        new_seg = {}
        for k in ("start", "control1", "control2", "end"):
            p = seg[k]
            p1 = rotate_pt(p, pivot, theta1)
            p2 = rotate_pt(p1, joint_pivot_after_stage1, theta2 * w[k])
            new_seg[k] = [p2[0], p2[1] + bob]
        out.append(new_seg)
    return out


def transform_distal_rigid(locked_segs, pivot, joint_rest, theta1, theta2, bob):
    """For a component (hand/foot) rigidly attached at a limb's distal end:
    apply the SAME two-stage composition as the limb's own weight=1 points
    (stage1 rotate by theta1 around the hip/shoulder pivot, stage2 rotate
    by the FULL theta2 around the stage1-transformed joint), so the
    attachment stays exactly continuous with the limb's own tip."""
    joint_after_stage1 = rotate_pt(joint_rest, pivot, theta1)
    out = []
    for seg in locked_segs:
        new_seg = {}
        for k in ("start", "control1", "control2", "end"):
            p1 = rotate_pt(seg[k], pivot, theta1)
            p2 = rotate_pt(p1, joint_after_stage1, theta2)
            new_seg[k] = [p2[0], p2[1] + bob]
        new_seg_out = new_seg
        out.append(new_seg_out)
    return out


def transform_rigid(locked_segs, pivot, theta, bob):
    """The EXISTING (unchanged) single-pivot rigid rotation, for parts that
    remain rigid (hands/feet, or theta2=0 case)."""
    out = []
    for seg in locked_segs:
        new_seg = {}
        for k in ("start", "control1", "control2", "end"):
            p = rotate_pt(seg[k], pivot, theta)
            new_seg[k] = [p[0], p[1] + bob]
        out.append(new_seg)
    return out
