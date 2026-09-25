"""Fatigue and readiness scoring.

Blends session RPE drift, per-session performance drop, and check-in readiness
(sleep, energy, soreness) into a single 0–1 score. Also provides auto-deload
recommendation based on accumulated fatigue and plateau signals.
"""
from __future__ import annotations

from dataclasses import dataclass

from .thresholds import (
    DELOAD_FATIGUE_MIN_SESSIONS,
    DELOAD_FATIGUE_TRIGGER,
    DELOAD_FATIGUE_WINDOW,
    DELOAD_PLATEAU_TRIGGER,
    PLATEAU_ACTION_COUNT,
)


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


@dataclass
class DeloadRecommendation:
    should_deload: bool
    reason: str
    severity: str = "action"


def should_recommend_deload(
    recent_fatigue_scores: list[float],
    plateau_counts: dict[int, int],
    block_week: int | None = None,
    block_length: int | None = None,
) -> DeloadRecommendation | None:
    """Determine whether to recommend a deload based on accumulated signals.

    Triggers (any one is sufficient):
    1. Fatigue >= 0.7 on >= 2 of last 3 sessions.
    2. >= 3 exercises at plateau_count >= 4.
    3. Block week >= block_length (scheduled deload).
    """
    # Trigger 1: sustained high fatigue
    window = recent_fatigue_scores[-DELOAD_FATIGUE_WINDOW:]
    high_count = sum(1 for f in window if f >= DELOAD_FATIGUE_TRIGGER)
    if high_count >= DELOAD_FATIGUE_MIN_SESSIONS:
        return DeloadRecommendation(
            should_deload=True,
            reason=f"fatigue score >= {DELOAD_FATIGUE_TRIGGER} in "
                   f"{high_count} of last {len(window)} sessions",
        )

    # Trigger 2: widespread plateau
    plateaued = sum(1 for c in plateau_counts.values() if c >= PLATEAU_ACTION_COUNT)
    if plateaued >= DELOAD_PLATEAU_TRIGGER:
        return DeloadRecommendation(
            should_deload=True,
            reason=f"{plateaued} exercises at plateau (>= {PLATEAU_ACTION_COUNT} stalled exposures)",
        )

    # Trigger 3: block length reached
    if block_week is not None and block_length is not None and block_week >= block_length:
        return DeloadRecommendation(
            should_deload=True,
            reason=f"block week {block_week} >= planned length {block_length}; scheduled deload",
            severity="info",
        )

    return None
