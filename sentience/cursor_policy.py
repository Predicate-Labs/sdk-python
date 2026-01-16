"""
Human-like cursor movement policy + metadata.

This is intentionally SDK-local (no snapshot schema changes). It is used by actions to:
- generate more realistic mouse movement (multiple moves with easing, optional overshoot/jitter)
- emit trace/debug metadata describing the movement path
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class CursorPolicy:
    """
    Policy for cursor movement.

    - mode="instant": current behavior (single click without multi-step motion)
    - mode="human": move with a curved path + optional jitter/overshoot
    """

    mode: str = "instant"  # "instant" | "human"

    # Motion shaping (human mode)
    steps: int | None = None
    duration_ms: int | None = None
    jitter_px: float = 1.0
    overshoot_px: float = 6.0
    pause_before_click_ms: int = 20

    # Determinism hook for tests/repro
    seed: int | None = None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ease_in_out(t: float) -> float:
    # Smoothstep-ish easing
    return t * t * (3 - 2 * t)


def _bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return (x, y)


def build_human_cursor_path(
    *,
    start: tuple[float, float],
    target: tuple[float, float],
    policy: CursorPolicy,
) -> dict:
    """
    Build a human-like cursor path and metadata.

    Returns a dict suitable for attaching to ActionResult/trace payloads:
      {
        "mode": "human",
        "from": {"x":..., "y":...},
        "to": {"x":..., "y":...},
        "steps": ...,
        "duration_ms": ...,
        "pause_before_click_ms": ...,
        "jitter_px": ...,
        "overshoot_px": ...,
        "path": [{"x":..., "y":..., "t":...}, ...]
      }
    """
    rng = random.Random(policy.seed)

    x0, y0 = start
    x1, y1 = target
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)

    # Defaults based on distance (bounded)
    steps = int(policy.steps if policy.steps is not None else _clamp(10 + dist / 25.0, 12, 40))
    duration_ms = int(
        policy.duration_ms if policy.duration_ms is not None else _clamp(120 + dist * 0.9, 120, 700)
    )

    # Control points: offset roughly perpendicular to travel direction
    if dist < 1e-6:
        dist = 1.0
    ux, uy = dx / dist, dy / dist
    px, py = -uy, ux
    curve_mag = _clamp(dist / 3.5, 10.0, 140.0)
    curve_mag *= rng.uniform(0.5, 1.2)

    c1 = (x0 + dx * 0.25 + px * curve_mag, y0 + dy * 0.25 + py * curve_mag)
    c2 = (x0 + dx * 0.75 - px * curve_mag, y0 + dy * 0.75 - py * curve_mag)

    overshoot = float(policy.overshoot_px or 0.0)
    overshoot_point = (x1 + ux * overshoot, y1 + uy * overshoot) if overshoot > 0 else (x1, y1)

    pts: list[dict] = []
    for i in range(steps):
        t_raw = 0.0 if steps <= 1 else i / (steps - 1)
        t = _ease_in_out(t_raw)
        bx, by = _bezier((x0, y0), c1, c2, overshoot_point, t)

        # Small jitter, decaying near target
        jitter_scale = float(policy.jitter_px) * (1.0 - t_raw) * 0.9
        jx = rng.uniform(-jitter_scale, jitter_scale)
        jy = rng.uniform(-jitter_scale, jitter_scale)

        pts.append({"x": bx + jx, "y": by + jy, "t": round(t_raw, 4)})

    # If we overshot, add a small correction segment back to target.
    if overshoot > 0:
        pts.append({"x": x1, "y": y1, "t": 1.0})

    return {
        "mode": "human",
        "from": {"x": x0, "y": y0},
        "to": {"x": x1, "y": y1},
        "steps": steps,
        "duration_ms": duration_ms,
        "pause_before_click_ms": int(policy.pause_before_click_ms),
        "jitter_px": float(policy.jitter_px),
        "overshoot_px": overshoot,
        # Keep path bounded for trace size
        "path": pts[:64],
    }
