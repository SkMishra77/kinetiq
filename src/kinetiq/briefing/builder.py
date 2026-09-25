"""Build the ``get_briefing`` payload from repo functions."""
from __future__ import annotations

from ..db.connection import Database
from ..db.repos import analysis as anal
from ..db.repos import checkins as ck
from ..db.repos import issues as iss
from ..db.repos import profile as pr
from ..db.repos import programs as prg
from ..db.repos import workouts as wr
from ..domain.dates import today


def build(db: Database, tz: str, detail: str = "compact",
          recent_sessions: int = 5) -> dict:
    prof = pr.profile_snapshot(db)
    onboarding = pr.missing_onboarding(prof)

    program = prg.program_with_templates(db)

    recent = wr.workouts_since(db, limit=recent_sessions)
    for w in recent:
        # attach analysis summary
        a = db.execute("SELECT summary, performance_score FROM session_analyses WHERE workout_id=?",
                        (w["id"],)).fetchone()
        if a:
            w["analysis_summary"] = a["summary"]
            w["performance_score"] = a["performance_score"]

    dsm = wr.days_since_muscle(db, tz=tz)
    open_ins = anal.get_open_insights(db)
    pending = anal.get_pending_adjustments(db)
    prs = anal.recent_prs(db)
    bw = ck.bodyweight_trend(db)
    ready = ck.latest_readiness(db)
    open_issue_rows = iss.open_issues(db)

    # Weekly volume check
    from ..engine.volume import check_volume_bands, weekly_hard_sets
    vol_entries = wr.weekly_volume_entries(db)
    muscle_sets = weekly_hard_sets(vol_entries)
    goal = prof.get("primary_goal") or "muscle_gain"
    volume_flags = check_volume_bands(muscle_sets, goal)

    # Frequency check
    from ..engine.frequency import check_frequency
    days_per_week = prof.get("days_per_week") or 3
    frequency_flags = check_frequency(dsm, goal, days_per_week)

    # Muscle readiness (enriched days_since_muscle)
    from ..engine.recovery import muscle_readiness
    sleep_avg = ready.get("sleep_hours_avg")
    muscle_ready = muscle_readiness(dsm, muscle_sets, sleep_avg)

    # Physique proportionality (aesthetic goals only)
    from ..engine.proportions import assess_proportions
    from ..engine.thresholds import AESTHETIC_VOLUME_PRIORITIES
    physique_balance = None
    if goal in AESTHETIC_VOLUME_PRIORITIES:
        measurements = pr.latest_measurements(db)
        if measurements:
            report = assess_proportions(measurements, goal)
            physique_balance = {
                "goal": report.goal,
                "score": report.score,
                "ratios": report.ratios,
                "targets": report.targets,
                "lagging": [
                    {"muscles": lp.muscles, "ratio": lp.ratio_name,
                     "current": lp.current, "target": lp.target,
                     "gap_pct": lp.gap_pct, "suggestion": lp.suggestion}
                    for lp in report.lagging
                ],
                "symmetry_issues": report.symmetry_issues,
            }

    # rotation position
    rotation = None
    next_template = None
    if program and program.get("templates"):
        idx = program["next_template_index"] or 0
        idx = idx % len(program["templates"])
        rotation = {"position": idx + 1, "of": len(program["templates"])}
        nt = program["templates"][idx]
        next_template = {
            "id": nt["id"], "name": nt["name"], "order_no": nt["order_no"],
            "focus": nt["focus"], "target_muscles": nt["target_muscles"],
        }

    state = "ready"
    if onboarding:
        state = "needs_onboarding"
    elif not program:
        state = "needs_program"

    guidance = _guidance_for(state, open_ins)
    payload = {
        "today": today(tz).isoformat(),
        "timezone": tz,
        "state": state,
        "onboarding_missing": onboarding,
        "trainer_directives": [
            "Base loads on suggested_load from plan_next_session; explain deviations.",
            "Pain flags override progression.",
            "After the user reports a workout, call log_workout; then explain the analysis.",
            "Never re-ask what this briefing already returned.",
        ],
        "profile": {
            "display_name": prof.get("display_name"),
            "date_of_birth": prof.get("date_of_birth"),
            "age_years": prof.get("age_years"),
            "sex": prof.get("sex"),
            "height_cm": prof.get("height_cm"),
            "training_experience": prof.get("training_experience"),
            "primary_goal": prof.get("primary_goal"),
            "secondary_goals": prof.get("secondary_goals"),
            "days_per_week": prof.get("days_per_week"),
            "session_minutes": prof.get("session_minutes"),
            "gym_type": prof.get("gym_type"),
            "preferred_effort_scale": prof.get("preferred_effort_scale"),
            "equipment_summary": [e["equipment"] for e in (prof.get("equipment") or [])
                                    if e.get("available")],
        },
        "constraints": {
            "cannot": [p["ex_name"] for p in (prof.get("preferences") or []) if p["kind"] == "cannot"],
            "avoid": [p["ex_name"] for p in (prof.get("preferences") or []) if p["kind"] == "avoid"],
            "active_issues": open_issue_rows[:5],
            "limitations": prof.get("limitations") or [],
        },
        "program": {
            "id": program["id"] if program else None,
            "name": program["name"] if program else None,
            "split": program["split_type"] if program else None,
            "progression_model": program["progression_model"] if program else None,
            "rotation": rotation,
            "next_template": next_template,
            "active_block": program["active_block"] if program else None,
        },
        "recent_sessions": recent,
        "days_since_muscle": dsm,
        "muscle_readiness": muscle_ready,
        "weekly_volume": muscle_sets,
        "volume_flags": [
            {"muscle": f.muscle, "sets": f.sets, "band": (f.band_low, f.band_high),
             "status": f.status, "severity": f.severity}
            for f in volume_flags
        ],
        "frequency_flags": [
            {"muscle": f.muscle, "days_since": f.days_since,
             "threshold_days": f.threshold_days, "severity": f.severity}
            for f in frequency_flags
        ],
        "physique_balance": physique_balance,
        "open_insights": open_ins[:10],
        "pending_adjustments": pending[:10],
        "recent_prs": prs[:8],
        "bodyweight_trend": bw,
        "readiness": ready,
        "suggested_next_call": _suggested(state),
        "guidance": guidance,
    }
    if detail == "compact":
        # trim recent sessions to lightweight summaries
        payload["recent_sessions"] = [
            {"id": w["id"], "performed_on": w["performed_on"], "status": w["status"],
             "summary": w.get("analysis_summary"),
             "performance_score": w.get("performance_score")}
            for w in recent
        ]
    return payload


def _guidance_for(state: str, open_insights: list[dict]) -> str:
    if state == "needs_onboarding":
        return ("Onboarding is incomplete. Interview the user conversationally for the "
                "missing fields and call save_profile.")
    if state == "needs_program":
        return ("Profile is set. Design a program (search_knowledge / compare_exercises for "
                "exercise selection) and call create_program.")
    action = next((i for i in open_insights if i.get("severity") == "action"), None)
    if action:
        return f"Address open action: {action.get('title')} — {action.get('detail')}."
    return ("Ready for training. For 'what should I do today' call plan_next_session; "
            "after the user reports a workout call log_workout.")


def _suggested(state: str) -> str:
    if state == "needs_onboarding":
        return "save_profile"
    if state == "needs_program":
        return "create_program"
    return "plan_next_session"
