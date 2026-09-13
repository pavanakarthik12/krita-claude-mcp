"""StopAction (Phase 2G) - walk -> stop with deceleration.

Reuses WalkAction's own leg-contact/arm/torso formulas unchanged (wraps a
WalkAction instance rather than duplicating its math) but multiplies
stride/bounce/speed by a smooth decay envelope over `duration`, while
keeping the underlying gait OSCILLATOR running at the walk's original
constant frequency - only the amplitude (how big each step/swing is) decays
to zero, not the timing. That produces "shorter stride, reduced velocity,
settle" exactly as specified, without an abrupt cut from full stride to a
dead stop.

world_delta is the closed-form integral of the decaying speed (not a
re-evaluation trick) so position stays a pure, deterministic function of
time even while velocity is continuously changing.
"""
from typing import Optional

from .base import Action
from .walk import WalkAction
from ..pose import Pose


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _decay(x: float) -> float:
    return 1.0 - _smoothstep(x)


def _decay_integral(x: float) -> float:
    """Antiderivative of _decay(t/D) evaluated at x=t/D, i.e.
    integral_0^x (1 - 3u^2 + 2u^3) du = x - x^3 + 0.5*x^4."""
    x = max(0.0, min(1.0, x))
    return x - x ** 3 + 0.5 * x ** 4


class StopAction(Action):
    affected_bones = WalkAction.affected_bones

    def __init__(self):
        self._walk = WalkAction()

    def evaluate(self, time: float, params: dict, context: Optional[dict] = None) -> Pose:
        duration = params.get("duration", 1.0)
        initial_stride = params.get("initial_stride", 1.0)
        initial_bounce = params.get("initial_bounce", 1.0)
        initial_speed = params.get("initial_speed", 90.0)
        gait_hz = params.get("gait_hz", 1.0)

        envelope = _decay(time / duration) if duration > 0 else 0.0

        walk_params = {
            "speed": initial_speed,       # foot-contact timing uses the ORIGINAL speed
            "gait_hz": gait_hz,           # oscillator keeps running at constant rate
            "stride": initial_stride * envelope,
            "bounce": initial_bounce * envelope,
            "direction": params.get("direction", 1.0),
        }
        return self._walk.evaluate(time, walk_params, context)

    def world_delta(self, time: float, params: dict):
        duration = params.get("duration", 1.0)
        initial_speed = params.get("initial_speed", 90.0)
        direction = params.get("direction", 1.0)

        if duration <= 0:
            return (0.0, 0.0)

        x = min(time, duration) / duration
        displacement = initial_speed * direction * duration * _decay_integral(x)
        return (displacement, 0.0)
