"""Muscle recovery estimation — replaces raw days_since with readiness status.

Pure function. No DB or I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

LARGE_MUSCLES = frozenset({
    "quads", "hamstrings", "glutes", "lats", "chest", "upper_back",
})
SMALL_MUSCLES = frozenset({
    "biceps", "triceps", "forearms", "calves", "front_delts", "side_delts",
    "rear_delts", "abs", "obliques",
})

BASE_RECOVERY_HOURS_LARGE = 72
BASE_RECOVERY_HOURS_SMALL = 48
HIGH_VOLUME_PENALTY_HOURS = 12
POOR_SLEEP_PENALTY_HOURS = 12
HIGH_SORENESS_PENALTY_HOURS = 24


@dataclass
class RecoveryEstimate:
    muscle: str
    status: str            # 'recovered' | 'partial' | 'fatigued'
    recovery_pct: int      # 0-100
    days_since: int
    base_hours: int
    effective_hours: int


def estimate_recovery(
    muscle: str,
    days_since: int,
    volume_last: float = 0.0,
    intensity_last: float | None = None,
    sleep_avg: float | None = None,
    soreness: int | None = None,
) -> RecoveryEstimate:
    """Estimate recovery status for a muscle group.

    Args:
        muscle: Canonical muscle name.
        days_since: Days since the muscle was last trained.
        volume_last: Hard sets the muscle received last session.
        intensity_last: Avg RPE of that session (unused currently, reserved).
        sleep_avg: Average sleep hours over last 3 days.
        soreness: Self-reported soreness 0-5 for this muscle.
    """
    if muscle in LARGE_MUSCLES:
        base = BASE_RECOVERY_HOURS_LARGE
    elif muscle in SMALL_MUSCLES:
        base = BASE_RECOVERY_HOURS_SMALL
    else:
        base = (BASE_RECOVERY_HOURS_LARGE + BASE_RECOVERY_HOURS_SMALL) // 2

    effective = base
    if volume_last > 6:
        effective += HIGH_VOLUME_PENALTY_HOURS
    if sleep_avg is not None and sleep_avg < 6.5:
        effective += POOR_SLEEP_PENALTY_HOURS
    if soreness is not None and soreness >= 4:
        effective += HIGH_SORENESS_PENALTY_HOURS

    hours_elapsed = days_since * 24
    pct = min(100, int(round(hours_elapsed / max(1, effective) * 100)))

    if pct >= 100:
        status = "recovered"
    elif pct >= 60:
        status = "partial"
    else:
        status = "fatigued"

    return RecoveryEstimate(
        muscle=muscle,
        status=status,
        recovery_pct=pct,
        days_since=days_since,
        base_hours=base,
        effective_hours=effective,
    )


def muscle_readiness(
    days_since: dict[str, int],
    volume_by_muscle: dict[str, float] | None = None,
    sleep_avg: float | None = None,
    soreness_by_muscle: dict[str, int] | None = None,
) -> dict[str, dict]:
    """Compute recovery estimates for all muscles in ``days_since``."""
    vol = volume_by_muscle or {}
    sor = soreness_by_muscle or {}
    out: dict[str, dict] = {}
    for muscle, days in days_since.items():
        est = estimate_recovery(
            muscle, days,
            volume_last=vol.get(muscle, 0.0),
            sleep_avg=sleep_avg,
            soreness=sor.get(muscle),
        )
        out[muscle] = {
            "status": est.status,
            "recovery_pct": est.recovery_pct,
            "days_since": est.days_since,
        }
    return out
