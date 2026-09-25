"""Equipment-aware rounding of suggested loads."""
from __future__ import annotations

from .thresholds import DEFAULT_INCREMENTS


def increment_for(equipment: str, profile_overrides: dict[str, float] | None = None,
                  template_increment: float | None = None) -> float:
    if template_increment and template_increment > 0:
        return float(template_increment)
    if profile_overrides and equipment in profile_overrides:
        return float(profile_overrides[equipment])
    return float(DEFAULT_INCREMENTS.get(equipment, 2.5))


def round_load(value: float, increment: float, mode: str = "nearest") -> float:
    if increment <= 0:
        return round(value, 2)
    steps = value / increment
    if mode == "down":
        steps = int(steps)
    elif mode == "up":
        # ceiling
        steps = int(steps) + (1 if steps > int(steps) else 0)
    else:
        steps = round(steps)
    return round(steps * increment, 4)
