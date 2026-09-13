"""WalkAction - coordinated four-limb walk cycle, Phase 2 revision.

Two modes, chosen automatically:

  - context has an "asset" (the normal case - CharacterInstance always
    supplies it): legs are driven by a deterministic foot-contact model
    (plant / hold / release / swing / new plant, alternating per foot) fed
    through a standard closed-form 2-bone IK solve (ik2bone.py) - see that
    module's docstring for why this replaces DragonBones' own IK
    constraint. Arms/torso/head keep the same style of procedural rotation
    as Phase 1, tuned for smoother curves (2F).
  - no context/asset given: falls back to Phase 1's direct thigh/shin
    rotation formula. This keeps WalkAction usable standalone (exactly how
    tests/test_actions.py already calls it) without requiring a whole
    CharacterAsset just to unit-test the arm/torso formulas.

Locomotion (2A) is entirely separate from bone rotation: world_delta()
reports how far the character has moved in world space as a pure function
of local time - never baked into any bone's geometry.
"""
import math
from typing import Optional

from .base import Action
from ..ik2bone import solve_2bone_ik
from ..pose import BoneChannel, Pose

TWO_PI = 2.0 * math.pi


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


class WalkAction(Action):
    affected_bones = (
        "root", "torso", "head",
        "thigh_front", "shin_front", "thigh_back", "shin_back",
        "upper_arm_front", "forearm_front", "upper_arm_back", "forearm_back",
    )

    def evaluate(self, time: float, params: dict, context: Optional[dict] = None) -> Pose:
        speed = params.get("speed", 90.0)         # world units/sec
        gait_hz = params.get("gait_hz", 1.0)       # gait cycles/sec (leg swing rate)
        stride = params.get("stride", 1.0)         # amplitude multiplier
        bounce = params.get("bounce", 1.0)         # hip bounce multiplier
        direction = params.get("direction", 1.0)   # +1/-1 world-space travel direction

        # `direction` (+1/-1) only affects world_delta's sign - the leg
        # oscillator itself looks the same whichever way the body travels.
        phase = TWO_PI * gait_hz * time

        pose = Pose()

        asset = context.get("asset") if context else None
        if asset is not None and asset.leg_geometry:
            self._apply_leg_contact_ik(pose, phase, stride, speed, gait_hz, asset)
        else:
            self._apply_leg_fallback_rotation(pose, phase, stride)

        upper_arm_f = stride * 26.0 * math.sin(phase + math.pi)
        upper_arm_b = stride * 26.0 * math.sin(phase)
        forearm_f = stride * 14.0 * max(0.0, math.sin(phase + math.pi + math.pi / 2.0))
        forearm_b = stride * 14.0 * max(0.0, math.sin(phase + math.pi / 2.0))

        hip_bounce = -bounce * 6.0 * abs(math.sin(phase))
        # Smoothed (squared-sine, still fully closed-form/deterministic)
        # torso/head stabilization - 2F tuning: the plain sine used in
        # Phase 1 changed direction abruptly at each zero-crossing; using
        # sin(phase)*|sin(phase)| keeps the same period/zero-crossings but
        # rounds off the peak instead of arriving at it linearly, reading
        # as a softer, less mechanical counter-sway.
        s = math.sin(phase)
        torso_stabilize = -stride * 3.0 * s * abs(s)
        head_stabilize = stride * 1.5 * s * abs(s)

        pose.set_rotation("upper_arm_front", upper_arm_f)
        pose.set_rotation("forearm_front", forearm_f)
        pose.set_rotation("upper_arm_back", upper_arm_b)
        pose.set_rotation("forearm_back", forearm_b)
        pose.set_rotation("torso", torso_stabilize)
        pose.set_rotation("head", head_stabilize)

        root = pose.bones.get("root", BoneChannel())
        root.translation = (root.translation[0], hip_bounce)
        pose.bones["root"] = root
        return pose

    def _apply_leg_fallback_rotation(self, pose: Pose, phase: float, stride: float) -> None:
        """Phase 1's direct-rotation formula - used only when no
        CharacterAsset/foot-contact context is available (e.g. calling
        WalkAction directly in a unit test)."""
        thigh_f = stride * 30.0 * math.sin(phase)
        thigh_b = stride * 30.0 * math.sin(phase + math.pi)
        shin_f = stride * 22.0 * max(0.0, math.sin(phase + math.pi / 2.0))
        shin_b = stride * 22.0 * max(0.0, math.sin(phase + math.pi + math.pi / 2.0))
        pose.set_rotation("thigh_front", thigh_f)
        pose.set_rotation("shin_front", shin_f)
        pose.set_rotation("thigh_back", thigh_b)
        pose.set_rotation("shin_back", shin_b)

    def _apply_leg_contact_ik(self, pose: Pose, phase: float, stride: float, speed: float, gait_hz: float, asset) -> None:
        """Phase 2B/2C: for each foot, compute where it should be right
        now (planted-and-holding, or mid-swing-arc) in the character's own
        rig-local space, then solve the 2-bone IK to reach it."""
        # Duration of one stance (== one swing) phase, and how far the body
        # travels (hence how far a planted foot drifts backward relative
        # to the hip) during that phase - see this method's docstring.
        stance_duration = (0.5 / gait_hz) if gait_hz > 0 else 0.0
        stance_travel = speed * stance_duration
        half_stride = 0.5 * stance_travel * stride
        lift_height = 26.0 * stride

        for side, foot_phase in (("front", phase), ("back", phase + math.pi)):
            geom = asset.leg_geometry[side]
            # Foot's neutral ("ankle on the ground, directly under the
            # hip") position - the contact model oscillates fore/aft and
            # up/down AROUND this point, entirely in rig-local space; the
            # separate world_delta() channel is what actually advances the
            # character through the scene.
            #
            # This leg is dead straight at rest (thigh/shin share the same
            # rest rotation), so a target at exactly hip_x+(L1+L2) sits
            # right at 2-bone IK's maximally-sensitive fully-extended
            # point, where the solved angle changes very fast for a tiny
            # target movement - empirically (see walk_probe.py) this
            # produced a visible knee "pop" a few frames into stance, not
            # a real discontinuity in the target itself. A small reach
            # slack (leg neutrally ~7% short of full extension, a barely
            # visible bend) keeps the whole stance sweep in a numerically
            # calm region instead.
            reach = 0.93 * (geom.upper_length + geom.lower_length)
            rest_x = geom.hip_x + reach * math.cos(geom.rest_angle_rad)
            rest_y = geom.hip_y + reach * math.sin(geom.rest_angle_rad)

            local_phase = (foot_phase % TWO_PI) / TWO_PI  # 0..1
            if local_phase < 0.5:
                # STANCE: foot is planted. It starts (touchdown) ahead of
                # the hip and drifts straight back to behind the hip as
                # the body moves forward over it - a planted foot, not a
                # slide, once the outer world_delta translation is added
                # back on top at render time.
                s = local_phase / 0.5  # 0..1 across stance
                target_x = rest_x + half_stride - s * 2.0 * half_stride
                target_y = rest_y
            else:
                # SWING: arc the foot forward through the air from behind
                # the hip back to ahead of it, lifting clear of the ground
                # at mid-swing - continuous with stance at both ends.
                u = (local_phase - 0.5) / 0.5  # 0..1 across swing
                eased = _smoothstep(u)
                target_x = rest_x - half_stride + eased * 2.0 * half_stride
                target_y = rest_y - lift_height * math.sin(math.pi * u)

            upper_delta, lower_delta = solve_2bone_ik(target_x, target_y, geom)
            pose.set_rotation(f"thigh_{side}", upper_delta)
            pose.set_rotation(f"shin_{side}", lower_delta)

    def world_delta(self, time: float, params: dict):
        speed = params.get("speed", 90.0)
        direction = params.get("direction", 1.0)
        return (speed * direction * time, 0.0)
