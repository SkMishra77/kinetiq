"""Weekly hard-set counting per muscle and volume-band checking."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .thresholds import AESTHETIC_VOLUME_PRIORITIES, WEEKLY_VOLUME_BANDS


def weekly_hard_sets(
    entries: list[dict],
) -> dict[str, float]:
    """Given a list of ``{'primary': [...], 'secondary': [...], 'working_sets': int}``
    for the last 7 days, return a ``{muscle: sets}`` map.

    Secondary muscles count 0.5. Working sets exclude warm-ups.
    """
    tally: dict[str, float] = defaultdict(float)
    for e in entries:
        n = float(e.get("working_sets", 0))
        for m in e.get("primary", []):
            tally[m] += n
        for m in e.get("secondary", []):
            tally[m] += n * 0.5
    return dict(tally)


@dataclass
class VolumeFlag:
    muscle: str
    sets: float
    band_low: int
    band_high: int
    status: str          # 'under' | 'ok' | 'over'
    severity: str        # 'info' | 'watch'


def check_volume_bands(
    muscle_sets: dict[str, float],
    goal: str,
) -> list[VolumeFlag]:
    """Compare rolling 7-day hard sets per muscle against goal-specific bands.

    For aesthetic goals (aesthetic_vtaper, aesthetic_balanced, classic_physique)
    uses per-muscle bands from ``AESTHETIC_VOLUME_PRIORITIES``. For other goals
    uses the flat ``WEEKLY_VOLUME_BANDS``.

    Returns a flag for every muscle that is outside its band.
    Muscles inside the band are omitted (caller can infer 'ok').
    """
    aesthetic_map = AESTHETIC_VOLUME_PRIORITIES.get(goal)
    flat_band = WEEKLY_VOLUME_BANDS.get(goal, (8, 15))
    flags: list[VolumeFlag] = []
    for muscle, sets in sorted(muscle_sets.items()):
        if aesthetic_map and muscle in aesthetic_map:
            lo, hi = aesthetic_map[muscle]
        else:
            lo, hi = flat_band
        if sets < lo:
            flags.append(VolumeFlag(
                muscle=muscle, sets=sets, band_low=lo, band_high=hi,
                status="under", severity="info",
            ))
        elif sets > hi:
            flags.append(VolumeFlag(
                muscle=muscle, sets=sets, band_low=lo, band_high=hi,
                status="over", severity="watch",
            ))
    return flags
