"""Weekly hard-set counting per muscle."""
from __future__ import annotations
from collections import defaultdict


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
