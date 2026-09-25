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
    COMPOUND_LOWER_PATTERNS,
    INCREMENT_PCT_LOWER,
    INCREMENT_PCT_UPPER,
    LOAD_REDUCE_PCT_HYPERTROPHY,
    LOAD_REDUCE_PCT_LINEAR,
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


def decide_rpe_autoregulated(
    sets: list[SetSummary],
    target_rpe: float,
    increment_kg: float,
    rep_min: int = 1,
    rep_max: int = 12,
    movement_pattern: str = "other",
) -> ProgressionDecision:
    """RPE-based autoregulation.

    All working sets at or below target RPE → increase load by increment.
    Any set at RPE >= target + 1 → hold.
    Any set at RPE >= 9.5 with reps below rep_min → reduce 7.5%.
    Falls back to double_progression when no RPE data is present.
    """
    top = _top_working(sets)
    if not top or top.load_kg is None:
        return ProgressionDecision("hold", reason="no top set")
    L = top.load_kg
    working = [s for s in sets if not s.is_warmup and (s.reps or 0) > 0]
    if not working:
        return ProgressionDecision("hold", reason="no working sets")

    rpe_vals = [s.rpe for s in working if s.rpe is not None]
    if not rpe_vals:
        return decide_double_progression(
            sets, rep_min=rep_min, rep_max=rep_max,
            target_rir=max(0, int(round(10 - target_rpe))),
            increment_kg=increment_kg, movement_pattern=movement_pattern,
        )

    max_rpe = max(rpe_vals)
    avg_rpe = sum(rpe_vals) / len(rpe_vals)
    below_min = any((s.reps or 0) < rep_min for s in working)

    if below_min and max_rpe >= 9.5:
        pct = LOAD_REDUCE_PCT_HYPERTROPHY
        return ProgressionDecision(
            "reduce_load",
            next_load_kg=round_load(L * pct, increment_kg, "down"),
            next_rep_target=rep_min,
            reason=f"RPE {max_rpe} with reps below minimum; −{int((1-pct)*100)}%",
        )

    if avg_rpe <= target_rpe:
        pct = INCREMENT_PCT_LOWER if movement_pattern in COMPOUND_LOWER_PATTERNS else INCREMENT_PCT_UPPER
        delta = max(increment_kg, L * pct)
        nload = round_load(L + delta, increment_kg, "nearest")
        if nload <= L:
            nload = L + increment_kg
        return ProgressionDecision(
            "increase_load",
            next_load_kg=nload,
            next_rep_target=rep_min,
            reason=f"avg RPE {avg_rpe:.1f} ≤ target {target_rpe}; increasing load",
        )

    if max_rpe >= target_rpe + 1:
        return ProgressionDecision(
            "hold",
            next_load_kg=L,
            next_rep_target=rep_min,
            reason=f"RPE {max_rpe:.1f} exceeds target {target_rpe} + 1; holding",
        )

    return ProgressionDecision(
        "add_reps",
        next_load_kg=L,
        next_rep_target=min(rep_max, max((s.reps or 0) for s in working) + 1),
        reason=f"avg RPE {avg_rpe:.1f} near target; add reps before load",
    )


# ---- Wave config defaults ------------------------------------------------

DEFAULT_WAVE_PHASES: list[dict[str, int]] = [
    {"week": 1, "reps": 10, "sets": 3},
    {"week": 2, "reps": 8, "sets": 3},
    {"week": 3, "reps": 6, "sets": 3},
]


def decide_wave(
    sets: list[SetSummary],
    week_in_block: int,
    increment_kg: float,
    wave_phases: list[dict[str, int]] | None = None,
    movement_pattern: str = "other",
) -> ProgressionDecision:
    """Wave / undulating periodisation.

    Default 3-week waves: week 1 → 3×10, week 2 → 3×8 +load, week 3 → 3×6 +load.
    After the wave resets to week 1 at a higher baseline (+increment).

    The caller passes ``week_in_block`` (1-based). If the user completed all
    target reps for the current phase, we prescribe the next phase's load.
    """
    phases = wave_phases or DEFAULT_WAVE_PHASES
    cycle_len = len(phases)
    if cycle_len == 0:
        return ProgressionDecision("hold", reason="empty wave config")

    phase_idx = (week_in_block - 1) % cycle_len
    phase = phases[phase_idx]
    target_reps = phase["reps"]
    target_sets = phase.get("sets", 3)

    top = _top_working(sets)
    if not top or top.load_kg is None:
        return ProgressionDecision("hold", reason="no top set")
    L = top.load_kg
    working = [s for s in sets if not s.is_warmup and (s.reps or 0) > 0]
    if not working:
        return ProgressionDecision("hold", reason="no working sets")

    hit_all = all((s.reps or 0) >= target_reps for s in working)
    next_phase_idx = (phase_idx + 1) % cycle_len
    next_phase = phases[next_phase_idx]

    if hit_all:
        if next_phase_idx == 0:
            nload = round_load(L + increment_kg, increment_kg, "nearest")
            return ProgressionDecision(
                "increase_load",
                next_load_kg=nload,
                next_rep_target=next_phase["reps"],
                next_sets=next_phase.get("sets", target_sets),
                reason=f"wave cycle complete; reset to week 1 at +{increment_kg}kg",
            )
        pct = INCREMENT_PCT_LOWER if movement_pattern in COMPOUND_LOWER_PATTERNS else INCREMENT_PCT_UPPER
        delta = max(increment_kg, L * pct)
        nload = round_load(L + delta, increment_kg, "nearest")
        if nload <= L:
            nload = L + increment_kg
        return ProgressionDecision(
            "increase_load",
            next_load_kg=nload,
            next_rep_target=next_phase["reps"],
            next_sets=next_phase.get("sets", target_sets),
            reason=f"wave phase {phase_idx+1} complete; advance to phase {next_phase_idx+1}",
        )

    below_target = any((s.reps or 0) < target_reps for s in working)
    if below_target:
        return ProgressionDecision(
            "hold",
            next_load_kg=L,
            next_rep_target=target_reps,
            next_sets=target_sets,
            reason=f"wave phase {phase_idx+1}: missed target {target_reps} reps; repeat",
        )

    return ProgressionDecision(
        "hold", next_load_kg=L, next_rep_target=target_reps,
        next_sets=target_sets,
        reason=f"wave phase {phase_idx+1}: partial completion; hold",
    )
