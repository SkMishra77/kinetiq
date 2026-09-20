"""Fatigue and readiness scoring.

Blends session RPE drift, per-session performance drop, and check-in readiness
(sleep, energy, soreness) into a single 0–1 score.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class FatigueInputs:
    regressed_share: float = 0.0        # share of exercises this session that regressed
    rpe_drift: float = 0.0              # mean RPE of last 3 sessions − prior 3
    energy: int | None = None           # 1..5
    fatigue_level: int | None = None    # 1..5 (self-reported)
    sleep_hours: float | None = None
    sleep_quality: int | None = None
    soreness: int | None = None         # 0..5


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score(inp: FatigueInputs) -> float:
    """Return 0–1 fatigue score (0 = fresh, 1 = fried).

    Weights (renormalised for missing components):

    * 30 % regression share this session
    * 20 % RPE drift (over 3-session window)
    * 15 % low energy
    * 15 % high self-reported fatigue
    * 10 % short/poor sleep
    * 10 % soreness
    """
    parts: list[tuple[float, float]] = []  # (weight, contribution)
    parts.append((0.30, _clamp(inp.regressed_share)))
    parts.append((0.20, _clamp(inp.rpe_drift / 2.0)))   # +2 RPE drift → 1.0
    if inp.energy is not None:
        parts.append((0.15, _clamp((5 - inp.energy) / 4.0)))
    if inp.fatigue_level is not None:
        parts.append((0.15, _clamp((inp.fatigue_level - 1) / 4.0)))
    if inp.sleep_hours is not None:
        parts.append((0.10, _clamp((7.5 - inp.sleep_hours) / 3.0)))
    if inp.soreness is not None:
        parts.append((0.10, _clamp(inp.soreness / 5.0)))
    total_w = sum(w for w, _ in parts) or 1.0
    return round(sum(w * c for w, c in parts) / total_w, 3)
