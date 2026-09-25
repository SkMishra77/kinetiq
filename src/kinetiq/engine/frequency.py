"""Frequency analysis — flag muscles not trained often enough."""
from __future__ import annotations

from dataclasses import dataclass

FREQUENCY_THRESHOLDS: dict[str, int] = {
    "muscle_gain": 5,
    "recomposition": 5,
    "strength": 7,
    "fat_loss": 7,
    "general_fitness": 7,
    "endurance": 7,
    "athletic": 7,
}

HIGH_FREQUENCY_GOAL_DAYS_PER_WEEK = 4


@dataclass
class FrequencyFlag:
    muscle: str
    days_since: int
    threshold_days: int
    severity: str        # 'info' | 'watch'


def check_frequency(
    days_since: dict[str, int],
    goal: str,
    days_per_week: int = 3,
) -> list[FrequencyFlag]:
    """Flag muscles not trained within the goal-appropriate window.

    Higher-frequency goals (muscle_gain, recomposition) with >= 4 days/week
    use a 5-day threshold; others use 7 days.
    """
    base = FREQUENCY_THRESHOLDS.get(goal, 7)
    if goal in ("muscle_gain", "recomposition") and days_per_week >= HIGH_FREQUENCY_GOAL_DAYS_PER_WEEK:
        threshold = base
    else:
        threshold = max(base, 7)

    flags: list[FrequencyFlag] = []
    for muscle, days in sorted(days_since.items()):
        if days > threshold:
            severity = "watch" if days > threshold * 2 else "info"
            flags.append(FrequencyFlag(
                muscle=muscle,
                days_since=days,
                threshold_days=threshold,
                severity=severity,
            ))
    return flags
