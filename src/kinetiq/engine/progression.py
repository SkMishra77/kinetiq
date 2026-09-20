"""Progression rules per template exercise.

Given the completed sets and (optionally) the target rep range, pick a
``NextAction`` and (where applicable) the next load or reps target. Pure
functions over dataclasses — no DB access.
"""
from __future__ import annotations
from dataclasses import dataclass

from .e1rm import rir_from_rpe
from .increments import round_load
from .thresholds import (
    COMPOUND_LOWER_PATTERNS, INCREMENT_PCT_UPPER, INCREMENT_PCT_LOWER,
    LOAD_REDUCE_PCT_HYPERTROPHY, LOAD_REDUCE_PCT_LINEAR,
)


@dataclass
class SetSummary:
    load_kg: float | None
    reps: int
    rpe: float | None = None
    rir: int | None = None
    is_warmup: bool = False


@dataclass
class ProgressionDecision:
    next_action: str
    next_load_kg: float | None = None
    next_rep_target: int | None = None
    next_sets: int | None = None
    reason: str = ""


def _top_working(sets: list[SetSummary]) -> SetSummary | None:
    working = [s for s in sets if not s.is_warmup and s.reps and s.reps > 0]
    if not working:
        return None
    return max(working, key=lambda s: (s.load_kg or 0.0, s.reps or 0))


def _effective_rir(s: SetSummary) -> int | None:
    if s.rir is not None:
        return s.rir
    return rir_from_rpe(s.rpe)


def _all_reps(sets: list[SetSummary], rep_target: int) -> bool:
    working = [s for s in sets if not s.is_warmup]
    return bool(working) and all((s.reps or 0) >= rep_target for s in working)


def decide_double_progression(
    sets: list[SetSummary],
    rep_min: int,
    rep_max: int,
    target_rir: int,
    increment_kg: float,
    movement_pattern: str = "other",
) -> ProgressionDecision:
    """Standard hypertrophy default.

    All working sets ≥ rep_max at target RIR → ``increase_load``.
    All working sets ≥ rep_min → ``add_reps`` (hold load, aim +1).
    Any set below rep_min or RPE ≥ 9.5 → ``reduce_load``.
    """
    top = _top_working(sets)
    if not top or top.load_kg is None:
        return ProgressionDecision("hold", reason="no top set")
    L = top.load_kg
    working = [s for s in sets if not s.is_warmup and (s.reps or 0) > 0]
    if not working:
        return ProgressionDecision("hold", reason="no working sets")

    rir_vals = [_effective_rir(s) for s in working]
    rpe_vals = [s.rpe for s in working if s.rpe is not None]
    max_rpe = max(rpe_vals) if rpe_vals else None

    all_at_max = _all_reps(working, rep_max)
    all_at_min = _all_reps(working, rep_min)
    below_min = any((s.reps or 0) < rep_min for s in working)

    # High RPE + failing to hit min reps → reduce
    if below_min or (max_rpe is not None and max_rpe >= 9.5 and not all_at_min):
        pct = LOAD_REDUCE_PCT_HYPERTROPHY
        return ProgressionDecision(
            "reduce_load",
            next_load_kg=round_load(L * pct, increment_kg, "down"),
            next_rep_target=rep_min,
            reason=f"below rep_min or RPE ≥ 9.5; −{int((1-pct)*100)}%",
        )

    # Hit rep_max on every set (and effort left in the tank) → increase load
    effort_ok = True
    if any(r is not None for r in rir_vals):
        # At least one set has effort data; if any set is at 0 RIR while below rep_max, hold.
        min_rir_reported = min([r for r in rir_vals if r is not None], default=None)
        effort_ok = min_rir_reported is None or min_rir_reported >= max(0, target_rir - 1)

    if all_at_max and effort_ok:
        pct = INCREMENT_PCT_LOWER if movement_pattern in COMPOUND_LOWER_PATTERNS else INCREMENT_PCT_UPPER
        delta = max(increment_kg, L * pct)
        nload = round_load(L + delta, increment_kg, "nearest")
        if nload <= L:
            nload = L + increment_kg
        return ProgressionDecision(
            "increase_load",
            next_load_kg=nload,
            next_rep_target=rep_min,
            reason=f"all sets ≥ rep_max @ target RIR; +{increment_kg}kg (or +{int(pct*100)}%)",
        )

    if all_at_min:
        return ProgressionDecision(
            "add_reps",
            next_load_kg=L,
            next_rep_target=min(rep_max, max((s.reps or 0) for s in working) + 1),
            reason="hit rep_min on every set; aim +1 rep next time",
        )

    return ProgressionDecision("hold", next_load_kg=L, next_rep_target=rep_min,
                               reason="partial completion; hold load")


def decide_linear(
    sets: list[SetSummary],
    rep_target: int,
    increment_kg: float,
    consecutive_misses: int = 0,
    movement_pattern: str = "other",
) -> ProgressionDecision:
    """Novice-strength linear: hit all target reps → +increment; 2 misses → −10 %."""
    top = _top_working(sets)
    if not top or top.load_kg is None:
        return ProgressionDecision("hold", reason="no top set")
    L = top.load_kg
    working = [s for s in sets if not s.is_warmup]
    hit_all = bool(working) and all((s.reps or 0) >= rep_target for s in working)
    if hit_all:
        return ProgressionDecision(
            "increase_load",
            next_load_kg=round_load(L + increment_kg, increment_kg, "nearest"),
            next_rep_target=rep_target,
            reason="all sets hit target reps; +1 increment",
        )
    if consecutive_misses + 1 >= 2:
        return ProgressionDecision(
            "reduce_load",
            next_load_kg=round_load(L * LOAD_REDUCE_PCT_LINEAR, increment_kg, "down"),
            next_rep_target=rep_target,
            reason="two consecutive misses; −10 %",
        )
    return ProgressionDecision("hold", next_load_kg=L, next_rep_target=rep_target,
                               reason="missed but first attempt; hold")
