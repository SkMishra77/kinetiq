"""Assemble a full session plan from template + history + readiness."""
from __future__ import annotations
from dataclasses import dataclass, field

from .loads import LoadInputs, LoadPlan, compute as compute_load
from . import warmup as wu


@dataclass
class TemplateExerciseCtx:
    exercise_id: int
    slug: str
    name: str
    movement_pattern: str
    equipment: str
    primary_muscles: list[str]
    sets: int
    rep_min: int
    rep_max: int
    target_rir: int
    rest_s: int
    tempo: str | None
    role: str
    is_optional: bool
    superset_group: str | None
    increment_kg: float
    template_start_load: float | None = None
    # history / adjustments filled by service
    last_top_load: float | None = None
    last_e1rm: float | None = None
    last_analysis_next_load: float | None = None
    last_analysis_next_reps: int | None = None
    last_performed_on: str | None = None
    plateau_streak: int = 0
    trend: str | None = None
    pending_adj_load: float | None = None
    pending_adj_load_pct: float | None = None
    pending_adj_swap_to: int | None = None
    pending_adj_note: str | None = None
    issue_load_cap_pct: float | None = None
    substitutes: list[dict] = field(default_factory=list)


@dataclass
class PlannedExercise:
    order: int
    exercise: str
    exercise_id: int
    slug: str
    role: str
    sets: int
    rep_range: tuple[int, int]
    target_rir: int
    rest_s: int
    tempo: str | None
    suggested_load_kg: float | None
    mode: str
    basis: dict
    notes: list[str]
    last_performance: str | None
    substitutes: list[dict]
    warmup_ramp: list[dict]


@dataclass
class SessionPlan:
    date: str
    template_id: int | None
    template_name: str
    focus: str | None
    target_muscles: list[str]
    block: dict
    warmup: list[dict]
    cooldown: list[dict]
    exercises: list[PlannedExercise]
    est_minutes: int
    warnings: list[str]
    rationale: list[str]


def plan_session(
    *,
    date_iso: str,
    template_id: int | None,
    template_name: str,
    focus: str | None,
    target_muscles: list[str],
    block: dict,
    exercises: list[TemplateExerciseCtx],
    energy: int | None = None,
    sleep_hours: float | None = None,
    days_since_last: int | None = None,
    time_available_min: int | None = None,
) -> SessionPlan:
    planned: list[PlannedExercise] = []
    warnings: list[str] = []
    rationale: list[str] = []

    first_working_load: float | None = None
    for i, e in enumerate(exercises, start=1):
        lp: LoadPlan = compute_load(LoadInputs(
            increment_kg=e.increment_kg,
            pending_adj_load=e.pending_adj_load,
            pending_adj_load_pct=e.pending_adj_load_pct,
            pending_adj_swap_to=e.pending_adj_swap_to,
            last_analysis_next_load=e.last_analysis_next_load,
            last_top_load=e.last_top_load,
            template_start_load=e.template_start_load,
            block_load_multiplier=float(block.get("load_multiplier", 1.0)),
            issue_load_cap_pct=e.issue_load_cap_pct,
            days_since_last=days_since_last,
            energy=energy,
            sleep_hours=sleep_hours,
            template_sets=e.sets,
            rep_min=e.rep_min,
        ))
        if first_working_load is None and lp.suggested_load_kg is not None and e.role != "isolation":
            first_working_load = lp.suggested_load_kg
        planned.append(PlannedExercise(
            order=i,
            exercise=e.name,
            exercise_id=e.exercise_id,
            slug=e.slug,
            role=e.role,
            sets=lp.sets,
            rep_range=(e.rep_min, e.rep_max),
            target_rir=e.target_rir,
            rest_s=e.rest_s,
            tempo=e.tempo,
            suggested_load_kg=lp.suggested_load_kg,
            mode=lp.mode,
            basis=lp.basis,
            notes=lp.notes,
            last_performance=(
                f"last: {e.last_top_load}×{e.last_analysis_next_reps or ''} on {e.last_performed_on}"
                if e.last_top_load is not None else None
            ),
            substitutes=e.substitutes,
            warmup_ramp=[],  # filled below
        ))
        if lp.mode == "deload":
            rationale.append(f"{e.name}: deload load applied")

    # Ramp sets on the first compound
    if planned and first_working_load is not None:
        planned[0].warmup_ramp = wu.ramp_sets(first_working_load)

    # Time-budget trim
    est = _estimate_minutes(planned)
    if time_available_min and est > time_available_min:
        removed = []
        for pe in list(planned):
            if pe.role in ("isolation", "mobility") and pe.exercise_id in [x.exercise_id for x in exercises if x.is_optional]:
                planned.remove(pe)
                removed.append(pe.exercise)
                if _estimate_minutes(planned) <= time_available_min:
                    break
        if removed:
            warnings.append(f"dropped optional exercises to fit time: {', '.join(removed)}")

    warmup = wu.general_warmup() + wu.muscle_specific(target_muscles)
    cool = wu.cooldown(target_muscles)

    return SessionPlan(
        date=date_iso,
        template_id=template_id,
        template_name=template_name,
        focus=focus,
        target_muscles=target_muscles,
        block=block,
        warmup=warmup,
        cooldown=cool,
        exercises=planned,
        est_minutes=_estimate_minutes(planned),
        warnings=warnings,
        rationale=rationale,
    )


def _estimate_minutes(planned: list[PlannedExercise]) -> int:
    """Simple heuristic: sum of (sets × (rest + 45s)) / 60."""
    secs = 8 * 60  # warm-up + cooldown budget
    for pe in planned:
        set_time = pe.rest_s + 45
        secs += pe.sets * set_time
    return int(round(secs / 60))
