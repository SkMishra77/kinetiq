"""Session analyzer — combines per-exercise metrics, classification and next-action.

Pure Python. Takes normalised data structures (no DB rows) so it's trivially
testable. The service layer (``services.analysis``) is responsible for hydrating
inputs from SQLite and persisting outputs.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .e1rm import e1rm, rir_from_rpe
from .fatigue import FatigueInputs, score as fatigue_score
from .increments import round_load
from .pain import evaluate as evaluate_pain
from .progression import (
    ProgressionDecision, SetSummary,
    decide_double_progression, decide_linear,
)
from .thresholds import (
    ENGINE_VERSION,
    PROGRESSED_E1RM_PCT, PROGRESSED_TONNAGE_PCT,
    REGRESSED_E1RM_PCT, REGRESSED_TONNAGE_PCT,
)


# ---- Inputs --------------------------------------------------------------

@dataclass
class SetInput:
    load_kg: float | None = None
    added_kg: float | None = None
    assisted_kg: float | None = None
    reps: int | None = None
    duration_s: int | None = None
    distance_m: float | None = None
    rpe: float | None = None
    rir: int | None = None
    side: str = "both"
    is_warmup: bool = False
    to_failure: bool = False
    is_bodyweight: bool = False


@dataclass
class ExerciseInput:
    exercise_id: int
    slug: str
    name: str
    movement_pattern: str
    equipment: str
    increment_kg: float
    laterality: str = "bilateral"
    load_type: str = "external"
    bodyweight_load_factor: float = 1.0
    sets: list[SetInput] = field(default_factory=list)
    template_exercise_id: int | None = None
    rep_min: int | None = None
    rep_max: int | None = None
    target_rir: int = 2
    progression_rule: str = "double_progression"
    was_planned: bool = False
    skipped: bool = False
    feel: str | None = None
    pain_score: int | None = None
    form_notes: str | None = None
    # History
    prev_top_load_kg: float | None = None
    prev_best_e1rm_kg: float | None = None
    prev_tonnage_kg: float | None = None
    prev_avg_rpe: float | None = None
    prev_reps_at_top_load: int | None = None
    plateau_streak_before: int = 0
    previous_pain: list[int] | None = None
    bodyweight_kg: float | None = None
    linear_consecutive_misses: int = 0


# ---- Outputs -------------------------------------------------------------

@dataclass
class ComputedSet:
    set_no: int
    effective_load_kg: float | None
    volume_kg: float | None
    e1rm_kg: float | None
    e1rm_reliable: bool


@dataclass
class ExerciseVerdict:
    exercise_id: int
    slug: str
    name: str
    status: str
    top_load_kg: float | None
    reps_at_top_load: int | None
    best_e1rm_kg: float | None
    delta_e1rm_pct: float | None
    tonnage_kg: float
    delta_tonnage_pct: float | None
    avg_rpe: float | None
    rpe_delta: float | None
    hit_all_reps: bool | None
    hit_rep_max_all_sets: bool | None
    sets_completed: int
    sets_planned: int | None
    next_action: str
    next_load_kg: float | None
    next_rep_target: int | None
    next_sets: int | None
    reason: str
    workout_exercise_id: int | None = None
    prs: list[dict] = field(default_factory=list)
    pain_action: str | None = None
    pain_reason: str | None = None
    computed_sets: list[ComputedSet] = field(default_factory=list)


@dataclass
class SessionAnalysisOutput:
    engine_version: str
    per_exercise: list[ExerciseVerdict]
    performance_score: float
    fatigue_score: float
    adherence_pct: float | None
    flags: list[dict]
    summary: str


# ---- Helpers -------------------------------------------------------------

def _effective_load(s: SetInput, bodyweight_kg: float | None,
                    bw_factor: float, load_type: str) -> float | None:
    ext = s.load_kg if s.load_kg is not None else 0.0
    added = s.added_kg or 0.0
    assisted = s.assisted_kg or 0.0
    if s.is_bodyweight or load_type in ("bodyweight", "bodyweight_plus", "assisted"):
        if bodyweight_kg is None:
            return None
        return round(bodyweight_kg * bw_factor + added - assisted, 3)
    return round(ext + added - assisted, 3)


def _pct_delta(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100.0, 2)


def _summary_line(v: ExerciseVerdict) -> str:
    parts = [v.name]
    if v.top_load_kg is not None and v.reps_at_top_load is not None:
        parts.append(f"top {v.top_load_kg}×{v.reps_at_top_load}")
    if v.best_e1rm_kg is not None:
        parts.append(f"e1RM {v.best_e1rm_kg:.1f}")
    if v.delta_e1rm_pct is not None:
        parts.append(f"Δ{v.delta_e1rm_pct:+.1f}%")
    parts.append(v.status)
    return " · ".join(parts)


# ---- Main analyser -------------------------------------------------------

def analyse_exercise(ex: ExerciseInput) -> ExerciseVerdict:
    if ex.skipped:
        return ExerciseVerdict(
            exercise_id=ex.exercise_id, slug=ex.slug, name=ex.name,
            status="skipped", top_load_kg=None, reps_at_top_load=None,
            best_e1rm_kg=None, delta_e1rm_pct=None, tonnage_kg=0.0,
            delta_tonnage_pct=None, avg_rpe=None, rpe_delta=None,
            hit_all_reps=None, hit_rep_max_all_sets=None,
            sets_completed=0, sets_planned=None,
            next_action="hold", next_load_kg=None, next_rep_target=None,
            next_sets=None, reason="skipped",
        )

    computed: list[ComputedSet] = []
    working: list[tuple[SetInput, float | None, float | None, bool]] = []
    volume_total = 0.0
    for i, s in enumerate(ex.sets, start=1):
        eff = _effective_load(s, ex.bodyweight_kg, ex.bodyweight_load_factor, ex.load_type)
        vol = None
        e1_val, e1_ok = None, False
        if not s.is_warmup and s.reps is not None and eff is not None:
            vol = round(eff * s.reps, 3)
            volume_total += vol
            e1_val, e1_ok = e1rm(eff, s.reps, s.rir if s.rir is not None else rir_from_rpe(s.rpe))
            working.append((s, eff, e1_val, e1_ok))
        computed.append(ComputedSet(i, eff, vol, e1_val, e1_ok))

    if not working:
        return ExerciseVerdict(
            exercise_id=ex.exercise_id, slug=ex.slug, name=ex.name,
            status="incomplete", top_load_kg=None, reps_at_top_load=None,
            best_e1rm_kg=None, delta_e1rm_pct=None, tonnage_kg=0.0,
            delta_tonnage_pct=None, avg_rpe=None, rpe_delta=None,
            hit_all_reps=None, hit_rep_max_all_sets=None,
            sets_completed=0, sets_planned=None,
            next_action="hold", next_load_kg=None, next_rep_target=None,
            next_sets=None, reason="no working sets",
            computed_sets=computed,
        )

    top_set, top_eff, top_e1, top_e1_ok = max(working, key=lambda t: (t[1] or 0, t[0].reps or 0))
    top_reps = top_set.reps or 0
    reliable_e1 = max((e for _, _, e, ok in working if ok and e is not None), default=None)
    best_e1 = reliable_e1 if reliable_e1 is not None else top_e1

    # Effort metrics
    rpe_vals = [s.rpe for s, _, _, _ in working if s.rpe is not None]
    avg_rpe = round(sum(rpe_vals) / len(rpe_vals), 2) if rpe_vals else None
    rpe_delta = _pct_delta(avg_rpe, ex.prev_avg_rpe) if avg_rpe and ex.prev_avg_rpe else (
        round((avg_rpe - ex.prev_avg_rpe), 2) if avg_rpe is not None and ex.prev_avg_rpe is not None else None
    )

    hit_all = ex.rep_min is not None and all((s.reps or 0) >= ex.rep_min for s, *_ in working)
    hit_max = ex.rep_max is not None and all((s.reps or 0) >= ex.rep_max for s, *_ in working)

    # Classification
    delta_e1 = _pct_delta(best_e1, ex.prev_best_e1rm_kg)
    delta_tonn = _pct_delta(volume_total, ex.prev_tonnage_kg)
    status = _classify(
        delta_e1, delta_tonn, rpe_delta,
        prev_top_load=ex.prev_top_load_kg, cur_top_load=top_eff,
        prev_reps_top=ex.prev_reps_at_top_load, cur_reps_top=top_reps,
        no_history=ex.prev_best_e1rm_kg is None and ex.prev_top_load_kg is None,
    )

    # Pain override
    pain_rec = evaluate_pain(ex.pain_score, ex.previous_pain)
    next_action = "hold"
    next_load: float | None = None
    next_rep_target: int | None = None
    reason = ""

    if pain_rec.action == "stop":
        next_action = "swap"
        reason = pain_rec.reason
    elif pain_rec.action == "swap":
        next_action = "swap"
        reason = pain_rec.reason
    elif pain_rec.action == "reduce" and top_eff is not None:
        next_action = "reduce_load"
        next_load = round_load((top_eff or 0) * pain_rec.load_multiplier, ex.increment_kg, "down")
        next_rep_target = ex.rep_min
        reason = pain_rec.reason
    else:
        # Progression
        summaries = [
            SetSummary(load_kg=eff, reps=s.reps or 0, rpe=s.rpe, rir=s.rir, is_warmup=s.is_warmup)
            for s, eff, _, _ in [(s, e, e1, ok) for s, e, e1, ok in [(*t,) for t in working]]
        ]
        # Simpler: build directly from `working`
        summaries = [
            SetSummary(load_kg=eff, reps=s.reps or 0, rpe=s.rpe, rir=s.rir, is_warmup=False)
            for s, eff, _, _ in working
        ]
        if ex.progression_rule == "linear":
            dec = decide_linear(
                summaries, rep_target=ex.rep_min or top_reps,
                increment_kg=ex.increment_kg,
                consecutive_misses=ex.linear_consecutive_misses,
                movement_pattern=ex.movement_pattern,
            )
        else:
            dec = decide_double_progression(
                summaries,
                rep_min=ex.rep_min or (top_reps - 1 if top_reps > 1 else 1),
                rep_max=ex.rep_max or (top_reps + 2),
                target_rir=ex.target_rir,
                increment_kg=ex.increment_kg,
                movement_pattern=ex.movement_pattern,
            )
        next_action = dec.next_action
        next_load = dec.next_load_kg
        next_rep_target = dec.next_rep_target
        reason = dec.reason

    if status == "first_time" and pain_rec.action == "none":
        next_action = "hold"
        next_load = top_eff
        reason = "first exposure; baseline recorded"

    # PR detection
    prs: list[dict] = []
    if ex.prev_best_e1rm_kg is None or (best_e1 is not None and best_e1 > (ex.prev_best_e1rm_kg or 0) * 1.001):
        if best_e1 is not None:
            prs.append({"kind": "e1rm", "value": best_e1, "previous": ex.prev_best_e1rm_kg})
    if top_eff is not None and (ex.prev_top_load_kg is None or top_eff > ex.prev_top_load_kg):
        prs.append({"kind": "load", "value": top_eff, "reps": top_reps, "previous": ex.prev_top_load_kg})

    return ExerciseVerdict(
        exercise_id=ex.exercise_id, slug=ex.slug, name=ex.name,
        status=status,
        top_load_kg=top_eff,
        reps_at_top_load=top_reps,
        best_e1rm_kg=best_e1,
        delta_e1rm_pct=delta_e1,
        tonnage_kg=round(volume_total, 2),
        delta_tonnage_pct=delta_tonn,
        avg_rpe=avg_rpe,
        rpe_delta=rpe_delta,
        hit_all_reps=hit_all if ex.rep_min is not None else None,
        hit_rep_max_all_sets=hit_max if ex.rep_max is not None else None,
        sets_completed=len(working),
        sets_planned=None,
        next_action=next_action,
        next_load_kg=next_load,
        next_rep_target=next_rep_target,
        next_sets=None,
        reason=reason,
        prs=prs,
        pain_action=pain_rec.action if pain_rec.action != "none" else None,
        pain_reason=pain_rec.reason if pain_rec.action != "none" else None,
        computed_sets=computed,
    )


def _classify(
    delta_e1: float | None, delta_tonn: float | None, rpe_delta: float | None,
    prev_top_load: float | None, cur_top_load: float | None,
    prev_reps_top: int | None, cur_reps_top: int,
    no_history: bool,
) -> str:
    if no_history:
        return "first_time"
    # Reps-at-same-load progression
    reps_progress = (
        prev_top_load is not None and cur_top_load is not None
        and abs(prev_top_load - cur_top_load) < 0.01
        and prev_reps_top is not None and cur_reps_top >= prev_reps_top + 1
    )
    progressed = (
        (delta_e1 is not None and delta_e1 >= PROGRESSED_E1RM_PCT)
        or reps_progress
        or (delta_tonn is not None and delta_tonn >= PROGRESSED_TONNAGE_PCT
            and (rpe_delta is None or rpe_delta <= 1))
    )
    if progressed:
        return "progressed"
    regressed = (
        (delta_e1 is not None and delta_e1 <= REGRESSED_E1RM_PCT)
        or (delta_tonn is not None and delta_tonn <= REGRESSED_TONNAGE_PCT
            and (rpe_delta is None or rpe_delta >= 0))
    )
    if regressed:
        return "regressed"
    return "maintained"


def analyse_session(
    exercises: list[ExerciseInput],
    session_wellness: dict | None = None,
    sets_planned: int | None = None,
    prev_avg_rpe_3: float | None = None,
) -> SessionAnalysisOutput:
    per_ex: list[ExerciseVerdict] = [analyse_exercise(e) for e in exercises]

    non_skipped = [v for v in per_ex if v.status != "skipped"]
    if non_skipped:
        # performance score: +1 progressed/pr, 0 maintained/first_time, -1 regressed, -0.5 incomplete
        pts = {
            "progressed": 1.0,
            "maintained": 0.0,
            "first_time": 0.0,
            "regressed": -1.0,
            "incomplete": -0.5,
            "plateau": -0.25,
        }
        perf = sum(pts.get(v.status, 0.0) for v in non_skipped) / len(non_skipped)
    else:
        perf = 0.0

    # Fatigue
    regressed_share = (
        sum(1 for v in non_skipped if v.status == "regressed") / max(1, len(non_skipped))
    )
    cur_rpes = [v.avg_rpe for v in non_skipped if v.avg_rpe is not None]
    cur_avg_rpe = sum(cur_rpes) / len(cur_rpes) if cur_rpes else None
    rpe_drift = (cur_avg_rpe - prev_avg_rpe_3) if (cur_avg_rpe is not None and prev_avg_rpe_3 is not None) else 0.0

    w = session_wellness or {}
    fs = fatigue_score(FatigueInputs(
        regressed_share=regressed_share,
        rpe_drift=rpe_drift,
        energy=w.get("energy"),
        fatigue_level=w.get("fatigue"),
        sleep_hours=w.get("sleep_hours"),
        sleep_quality=w.get("sleep_quality"),
        soreness=w.get("soreness_level"),
    ))

    adherence = None
    if sets_planned:
        adherence = round(100.0 * sum(v.sets_completed for v in non_skipped) / max(1, sets_planned), 1)

    flags: list[dict] = []
    if fs >= 0.7:
        flags.append({"kind": "fatigue", "severity": "action",
                      "detail": "fatigue score high; consider a deload"})
    elif fs >= 0.5:
        flags.append({"kind": "fatigue", "severity": "watch", "detail": "elevated fatigue"})
    if regressed_share >= 0.4:
        flags.append({"kind": "recovery", "severity": "watch",
                      "detail": f"{int(regressed_share*100)} % of exercises regressed"})
    for v in non_skipped:
        if v.pain_action in ("stop", "swap"):
            flags.append({"kind": "pain", "severity": "action",
                          "exercise": v.name, "detail": v.pain_reason or ""})
        elif v.pain_action == "reduce":
            flags.append({"kind": "pain", "severity": "watch",
                          "exercise": v.name, "detail": v.pain_reason or ""})

    prs = sum(len(v.prs) for v in non_skipped)
    summary = f"{len(non_skipped)} exercises · perf {perf:+.2f} · fatigue {fs:.2f} · {prs} PR" + ("s" if prs != 1 else "")

    return SessionAnalysisOutput(
        engine_version=ENGINE_VERSION,
        per_exercise=per_ex,
        performance_score=round(perf, 3),
        fatigue_score=round(fs, 3),
        adherence_pct=adherence,
        flags=flags,
        summary=summary,
    )
