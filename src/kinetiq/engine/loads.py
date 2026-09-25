"""Suggested-load computation for the planner.

Priority (per exercise):

1. Pending ``next_session_adjustments`` (load / load_pct / swap / …)
2. Latest ``exercise_analyses.next_load_kg``
3. ``exercise_stats.last_top_load_kg``
4. Template ``start_weight_kg``
5. ``mode: "calibrate"`` — no history known

Modifiers applied in order:

* Block ``load_multiplier`` (deload / intensification blocks)
* Active-issue load cap (multiplier)
* Layoff (last session > 7 / > 21 days)
* Day-of readiness (low sleep or energy → ×0.95, −1 set)

Finally the load rounds to the exercise's increment.
"""
from __future__ import annotations

from dataclasses import dataclass

from .increments import round_load
from .thresholds import (
    LAYOFF_LOAD_PCT_LONG,
    LAYOFF_LOAD_PCT_MEDIUM,
    LAYOFF_LONG_DAYS,
    LAYOFF_MEDIUM_DAYS,
    LOAD_READINESS_REDUCE_PCT,
    LOW_ENERGY_THRESHOLD,
    LOW_SLEEP_HOURS,
)


@dataclass
class LoadInputs:
    increment_kg: float
    # sources of truth (any may be None)
    pending_adj_load: float | None = None
    pending_adj_load_pct: float | None = None
    pending_adj_swap_to: int | None = None
    pending_adj_note: str | None = None
    last_analysis_next_load: float | None = None
    last_top_load: float | None = None
    template_start_load: float | None = None
    # modifiers
    block_load_multiplier: float = 1.0
    issue_load_cap_pct: float | None = None
    days_since_last: int | None = None
    energy: int | None = None
    sleep_hours: float | None = None
    template_sets: int = 3
    # target reps
    rep_min: int = 8


@dataclass
class LoadPlan:
    suggested_load_kg: float | None
    sets: int
    rep_target: int
    mode: str            # 'progress' | 'hold' | 'reduce' | 'calibrate' | 'deload' | 'substituted'
    basis: dict
    notes: list[str]


def compute(inp: LoadInputs) -> LoadPlan:
    basis: dict = {"steps": []}
    notes: list[str] = []
    load: float | None = None
    mode = "hold"

    # 1) pending adjustment
    if inp.pending_adj_swap_to is not None:
        return LoadPlan(None, inp.template_sets, inp.rep_min, "substituted",
                        {"source": "pending_adjustment_swap"}, ["exercise swapped by prior adjustment"])
    if inp.pending_adj_load is not None:
        load = inp.pending_adj_load
        mode = "progress"
        basis["source"] = "pending_adjustment_load"
    elif inp.pending_adj_load_pct is not None and inp.last_top_load is not None:
        load = inp.last_top_load * (1.0 + inp.pending_adj_load_pct / 100.0)
        mode = "progress"
        basis["source"] = "pending_adjustment_load_pct"

    # 2) last analysis
    if load is None and inp.last_analysis_next_load is not None:
        load = inp.last_analysis_next_load
        mode = "progress"
        basis["source"] = "last_analysis_next_load"

    # 3) last top load
    if load is None and inp.last_top_load is not None:
        load = inp.last_top_load
        mode = "hold"
        basis["source"] = "last_top_load"

    # 4) template start
    if load is None and inp.template_start_load is not None:
        load = inp.template_start_load
        mode = "hold"
        basis["source"] = "template_start_load"

    if load is None:
        return LoadPlan(None, inp.template_sets, inp.rep_min, "calibrate",
                        {"source": "no_history"},
                        ["No history for this exercise — start with a working weight at RIR 2–3 "
                         "and log it; the next session will follow up."])

    # Modifiers ---------------------------------------------------------
    if inp.block_load_multiplier and abs(inp.block_load_multiplier - 1.0) > 1e-3:
        load = load * inp.block_load_multiplier
        basis["steps"].append(f"block load ×{inp.block_load_multiplier}")
        if inp.block_load_multiplier < 1.0:
            mode = "deload"
            notes.append(f"deload block: −{int((1 - inp.block_load_multiplier)*100)} %")

    if inp.issue_load_cap_pct and inp.issue_load_cap_pct < 1.0:
        load = min(load, (inp.last_top_load or load) * inp.issue_load_cap_pct)
        basis["steps"].append(f"issue cap ×{inp.issue_load_cap_pct}")
        notes.append(f"active issue caps load at {int(inp.issue_load_cap_pct*100)} %")

    if inp.days_since_last is not None:
        if inp.days_since_last > LAYOFF_LONG_DAYS:
            load = load * LAYOFF_LOAD_PCT_LONG
            basis["steps"].append(f"layoff>{LAYOFF_LONG_DAYS}d ×{LAYOFF_LOAD_PCT_LONG}")
            notes.append(f"long layoff ({inp.days_since_last} d); calibrate feel-based")
            mode = "calibrate"
        elif inp.days_since_last > LAYOFF_MEDIUM_DAYS:
            load = load * LAYOFF_LOAD_PCT_MEDIUM
            basis["steps"].append(f"layoff>{LAYOFF_MEDIUM_DAYS}d ×{LAYOFF_LOAD_PCT_MEDIUM}")
            notes.append(f"layoff of {inp.days_since_last} d; −{int((1 - LAYOFF_LOAD_PCT_MEDIUM)*100)} %")

    sets = inp.template_sets
    low_energy = inp.energy is not None and inp.energy <= LOW_ENERGY_THRESHOLD
    low_sleep = inp.sleep_hours is not None and inp.sleep_hours < LOW_SLEEP_HOURS
    if low_energy or low_sleep:
        load = load * LOAD_READINESS_REDUCE_PCT
        sets = max(1, sets - 1)
        basis["steps"].append(f"readiness ×{LOAD_READINESS_REDUCE_PCT}, −1 set")
        if mode == "progress":
            mode = "hold"
        notes.append("low readiness: reduced load & sets today")

    load = round_load(load, inp.increment_kg, "down" if mode == "reduce" else "nearest")
    return LoadPlan(load, sets, inp.rep_min, mode, basis, notes)
