"""Plateau detection and recommendations."""
from __future__ import annotations
from dataclasses import dataclass

from .thresholds import (
    PLATEAU_WARN_COUNT, PLATEAU_ACTION_COUNT, PLATEAU_MIN_SPAN_DAYS,
)


@dataclass
class PlateauResult:
    is_plateau: bool
    severity: str                    # 'info' | 'watch' | 'action'
    count: int
    reason: str
    suggested: list[str]


def check(streak: int, span_days: int, avg_rpe: float | None = None, working_sets: int = 3) -> PlateauResult:
    """Given the current no-progress streak and span, return a plateau verdict."""
    if streak < PLATEAU_WARN_COUNT or span_days < PLATEAU_MIN_SPAN_DAYS:
        return PlateauResult(False, "info", streak, "not plateaued", [])
    suggested: list[str] = []
    severity = "warn" if streak < PLATEAU_ACTION_COUNT else "action"
    if avg_rpe is not None and avg_rpe >= 9:
        suggested.append("deload")
    if working_sets < 3:
        suggested.append("add a working set")
    suggested.append("switch progression rule")
    suggested.append("swap variation")
    return PlateauResult(
        True,
        severity,
        streak,
        f"{streak} exposures without a progression best over {span_days} days",
        suggested,
    )
