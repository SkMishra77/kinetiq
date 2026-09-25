"""Workout / workout_exercises / sets SQL + a few analysis-adjacent queries."""
from __future__ import annotations

import json

from ..connection import Database


def create_workout(db: Database, *, performed_on: str, program_id: int | None,
                    template_id: int | None, planned_session_id: int | None,
                    block_id: int | None, status: str, wellness: dict,
                    raw_report: str | None, notes: str | None) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO workouts(performed_on, program_id, template_id, planned_session_id,
                                    block_id, status, session_rpe, energy, fatigue,
                                    sleep_hours, sleep_quality, stress, soreness_level,
                                    bodyweight_kg, notes, raw_report,
                                    created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (performed_on, program_id, template_id, planned_session_id, block_id, status,
             wellness.get("session_rpe"), wellness.get("energy"), wellness.get("fatigue"),
             wellness.get("sleep_hours"), wellness.get("sleep_quality"), wellness.get("stress"),
             wellness.get("soreness_level"), wellness.get("bodyweight_kg"),
             notes, raw_report),
        )
        return cur.lastrowid


def add_workout_exercise(db: Database, workout_id: int, *, order_no: int,
                          exercise_id: int, template_exercise_id: int | None,
                          was_planned: bool, skipped: bool,
                          feel: str | None, pain_score: int | None,
                          pain_location: str | None, form_notes: str | None,
                          notes: str | None) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO workout_exercises(workout_id, order_no, exercise_id,
                    template_exercise_id, was_planned, skipped, feel, pain_score,
                    pain_location, form_notes, notes)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workout_id, order_no, exercise_id, template_exercise_id,
             1 if was_planned else 0, 1 if skipped else 0,
             feel, pain_score, pain_location, form_notes, notes),
        )
        return cur.lastrowid


def add_set(db: Database, workout_exercise_id: int, *, set_no: int,
             load_kg: float | None, added_kg: float | None, assisted_kg: float | None,
             reps: int | None, duration_s: int | None, distance_m: float | None,
             rpe: float | None, rir: int | None, side: str = "both",
             is_warmup: bool = False, to_failure: bool = False,
             effective_load_kg: float | None = None, e1rm_kg: float | None = None,
             e1rm_reliable: bool = True, volume_kg: float | None = None,
             notes: str | None = None) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO sets(workout_exercise_id, set_no, load_kg, added_kg, assisted_kg,
                    reps, duration_s, distance_m, rpe, rir, side, is_warmup, to_failure,
                    effective_load_kg, e1rm_kg, e1rm_reliable, volume_kg, notes)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workout_exercise_id, set_no, load_kg, added_kg, assisted_kg,
             reps, duration_s, distance_m, rpe, rir, side,
             1 if is_warmup else 0, 1 if to_failure else 0,
             effective_load_kg, e1rm_kg, 1 if e1rm_reliable else 0,
             volume_kg, notes),
        )
        return cur.lastrowid


def previous_exposure(db: Database, exercise_id: int, before_on: str,
                       within_days: int = 90, template_exercise_id: int | None = None) -> dict | None:
    """Find the most-recent non-voided prior exposure for this exercise."""
    # Prefer same template_exercise_id if provided
    if template_exercise_id is not None:
        r = _prev(db, exercise_id, before_on, within_days, template_exercise_id)
        if r:
            return r
    return _prev(db, exercise_id, before_on, within_days, None)


def _prev(db: Database, exercise_id: int, before_on: str, within_days: int,
          template_exercise_id: int | None) -> dict | None:
    args = [exercise_id, before_on, before_on, within_days]
    tef = ""
    if template_exercise_id is not None:
        tef = " AND we.template_exercise_id=?"
        args.append(template_exercise_id)
    row = db.execute(
        f"""SELECT we.id AS wex_id, we.workout_id, w.performed_on, we.exercise_id,
                    we.pain_score, we.feel
             FROM workout_exercises we
             JOIN workouts w ON w.id=we.workout_id
            WHERE we.exercise_id=? AND we.skipped=0
              AND w.status IN ('completed','partial')
              AND w.performed_on < ?
              AND w.performed_on >= date(?, '-'||?||' days')
              {tef}
            ORDER BY w.performed_on DESC, we.id DESC LIMIT 1""",
        tuple(args),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def sets_for_wex(db: Database, wex_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM sets WHERE workout_exercise_id=? ORDER BY set_no", (wex_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def summarize_exercise_at(db: Database, wex_id: int) -> dict:
    """Compute quick metrics (top_load, best_e1rm, tonnage, avg_rpe, reps_top) for a prior wex row."""
    sets = sets_for_wex(db, wex_id)
    if not sets:
        return {}
    working = [s for s in sets if not s["is_warmup"] and (s["reps"] or 0) > 0]
    if not working:
        return {}
    top = max(working, key=lambda s: ((s["effective_load_kg"] or 0.0), s["reps"] or 0))
    tonnage = sum((s["volume_kg"] or 0.0) for s in working)
    e1 = max((s["e1rm_kg"] for s in working if s["e1rm_kg"] and s["e1rm_reliable"]), default=None)
    rpes = [s["rpe"] for s in working if s["rpe"] is not None]
    return {
        "top_load_kg": top["effective_load_kg"],
        "reps_at_top_load": top["reps"],
        "tonnage_kg": round(tonnage, 3),
        "best_e1rm_kg": e1,
        "avg_rpe": round(sum(rpes) / len(rpes), 2) if rpes else None,
    }


def workouts_since(db: Database, since: str | None = None, limit: int = 20) -> list[dict]:
    if since:
        rows = db.execute("SELECT * FROM workouts WHERE performed_on >= ? AND status <> 'voided' "
                          "ORDER BY performed_on DESC LIMIT ?", (since, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM workouts WHERE status <> 'voided' "
                          "ORDER BY performed_on DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def weekly_volume_entries(db: Database) -> list[dict]:
    """Return per-exercise entries for the last 7 days, shaped for ``weekly_hard_sets()``."""
    rows = db.execute(
        """SELECT e.primary_muscles, e.secondary_muscles,
                  COUNT(DISTINCT s.id) FILTER (WHERE s.is_warmup=0) AS working_sets
           FROM workout_exercises we
             JOIN workouts w ON w.id=we.workout_id
             JOIN exercises e ON e.id=we.exercise_id
             LEFT JOIN sets s ON s.workout_exercise_id=we.id
           WHERE w.status IN ('completed','partial')
             AND w.performed_on >= date('now','-7 days')
             AND we.skipped=0
           GROUP BY we.id""",
    ).fetchall()
    entries: list[dict] = []
    for r in rows:
        primary = json.loads(r["primary_muscles"]) if isinstance(r["primary_muscles"], str) else (r["primary_muscles"] or [])
        secondary = json.loads(r["secondary_muscles"]) if isinstance(r["secondary_muscles"], str) else (r["secondary_muscles"] or [])
        entries.append({
            "primary": primary,
            "secondary": secondary,
            "working_sets": r["working_sets"],
        })
    return entries


def days_since_muscle(db: Database, tz: str | None = None) -> dict[str, int]:
    """Compute days since each primary muscle was last trained (in the caller's tz)."""
    from ...domain.dates import today as _tz_today
    rows = db.execute("SELECT muscle, last_on FROM v_muscle_last_trained").fetchall()
    from datetime import date
    today_local = _tz_today(tz) if tz else date.today()
    out: dict[str, int] = {}
    for r in rows:
        try:
            d = date.fromisoformat(r["last_on"])
            out[r["muscle"]] = max(0, (today_local - d).days)
        except Exception:
            pass
    return out
