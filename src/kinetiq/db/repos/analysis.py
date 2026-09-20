"""Persist analyzer output into session_analyses / exercise_analyses / insights /
personal_records / next_session_adjustments and update exercise_stats.
"""
from __future__ import annotations
import json
from typing import Any

from ..connection import Database
from ...engine.analyzer import SessionAnalysisOutput


def store(db: Database, workout_id: int, out: SessionAnalysisOutput) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO session_analyses(workout_id, engine_version, computed_at,
                        performance_score, fatigue_score, adherence_pct,
                        summary, flags, details_json)
               VALUES(?, ?, datetime('now'), ?, ?, ?, ?, ?, ?)
               ON CONFLICT(workout_id) DO UPDATE SET
                        engine_version=excluded.engine_version,
                        computed_at=excluded.computed_at,
                        performance_score=excluded.performance_score,
                        fatigue_score=excluded.fatigue_score,
                        adherence_pct=excluded.adherence_pct,
                        summary=excluded.summary,
                        flags=excluded.flags,
                        details_json=excluded.details_json
               """,
            (workout_id, out.engine_version,
             out.performance_score, out.fatigue_score, out.adherence_pct,
             out.summary, json.dumps(out.flags), json.dumps({}),
             ),
        )
        sa_id = c.execute("SELECT id FROM session_analyses WHERE workout_id=?", (workout_id,)).fetchone()[0]
        c.execute("DELETE FROM exercise_analyses WHERE session_analysis_id=?", (sa_id,))
        for v in out.per_exercise:
            c.execute(
                """INSERT INTO exercise_analyses(session_analysis_id, workout_exercise_id,
                        exercise_id, status, e1rm_kg, e1rm_delta_pct, tonnage_kg,
                        tonnage_delta_pct, top_load_kg, reps_at_top_load,
                        avg_rpe, rpe_delta, hit_all_reps, hit_rep_max_all_sets,
                        sets_completed, next_action, next_load_kg, next_rep_target,
                        next_sets, reason)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sa_id, v.workout_exercise_id,
                 v.exercise_id, v.status, v.best_e1rm_kg, v.delta_e1rm_pct,
                 v.tonnage_kg, v.delta_tonnage_pct, v.top_load_kg, v.reps_at_top_load,
                 v.avg_rpe, v.rpe_delta,
                 None if v.hit_all_reps is None else int(v.hit_all_reps),
                 None if v.hit_rep_max_all_sets is None else int(v.hit_rep_max_all_sets),
                 v.sets_completed, v.next_action, v.next_load_kg, v.next_rep_target,
                 v.next_sets, v.reason),
            )
            # Update stats
            _update_stats(c, v, workout_id)
            # PRs
            for pr in v.prs:
                c.execute(
                    "INSERT INTO personal_records(exercise_id, kind, value, reps, load_kg, "
                    "workout_id, achieved_on, previous_value, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, date('now'), ?, datetime('now'))",
                    (v.exercise_id, pr["kind"], pr.get("value"),
                     pr.get("reps"), pr.get("value") if pr["kind"] == "load" else None,
                     workout_id, pr.get("previous")),
                )
            # Adjustment for next session
            if v.next_action in ("increase_load", "reduce_load", "swap"):
                payload = {
                    "load_kg": v.next_load_kg,
                    "reps": v.next_rep_target,
                    "sets": v.next_sets,
                    "next_action": v.next_action,
                }
                c.execute(
                    """INSERT INTO next_session_adjustments(created_at, source, exercise_id,
                            adjustment_type, value_json, reason, applies_until)
                       VALUES(datetime('now'), 'engine', ?, ?, ?, ?, date('now', '+21 days'))""",
                    (v.exercise_id,
                     "load" if v.next_action != "swap" else "swap",
                     json.dumps(payload), v.reason),
                )
        # Session-level flags → insights
        for flag in out.flags:
            _insert_insight(c, workout_id, flag)
        return sa_id


def _update_stats(c, v, workout_id: int) -> None:
    row = c.execute("SELECT * FROM exercise_stats WHERE exercise_id=?", (v.exercise_id,)).fetchone()
    now_iso = None
    best_e1 = v.best_e1rm_kg
    if row is None:
        c.execute(
            """INSERT INTO exercise_stats(exercise_id, sessions_count, first_performed_on,
                    last_performed_on, last_workout_id, best_e1rm_kg, best_e1rm_on,
                    best_load_kg, best_reps_at_best_load, last_e1rm_kg,
                    last_top_load_kg, last_top_reps, last_avg_rpe,
                    sessions_since_best, plateau_count, trend, updated_at)
               VALUES(?, 1, date('now'), date('now'), ?, ?, date('now'),
                      ?, ?, ?, ?, ?, ?, 0, 0, 'insufficient', datetime('now'))""",
            (v.exercise_id, workout_id, best_e1, v.top_load_kg, v.reps_at_top_load,
             best_e1, v.top_load_kg, v.reps_at_top_load, v.avg_rpe),
        )
        return
    prev_best = row["best_e1rm_kg"]
    new_best = prev_best if prev_best is not None else best_e1
    if best_e1 is not None and (prev_best is None or best_e1 > prev_best):
        new_best = best_e1
        best_e1_on = "date('now')"
        sessions_since_best = 0
    else:
        best_e1_on = None
        sessions_since_best = (row["sessions_since_best"] or 0) + (1 if v.status != "progressed" else 0)
    plateau_count = sessions_since_best
    # SQLite parameter approach — best_e1rm_on can't use datetime string easily, use SQL directly
    c.execute(
        f"""UPDATE exercise_stats SET
                sessions_count=sessions_count+1,
                last_performed_on=date('now'),
                last_workout_id=?,
                best_e1rm_kg=?,
                {"best_e1rm_on=date('now')," if best_e1_on else ""}
                best_load_kg=CASE WHEN ? IS NOT NULL AND (best_load_kg IS NULL OR ? > best_load_kg)
                                  THEN ? ELSE best_load_kg END,
                best_reps_at_best_load=CASE WHEN ? IS NOT NULL AND (best_load_kg IS NULL OR ? > best_load_kg)
                                            THEN ? ELSE best_reps_at_best_load END,
                last_e1rm_kg=?,
                last_top_load_kg=?,
                last_top_reps=?,
                last_avg_rpe=?,
                sessions_since_best=?,
                plateau_count=?,
                updated_at=datetime('now')
              WHERE exercise_id=?""",
        (workout_id, new_best,
         v.top_load_kg, v.top_load_kg, v.top_load_kg,
         v.top_load_kg, v.top_load_kg, v.reps_at_top_load,
         best_e1, v.top_load_kg, v.reps_at_top_load, v.avg_rpe,
         sessions_since_best, plateau_count,
         v.exercise_id),
    )


def _insert_insight(c, workout_id: int, flag: dict) -> None:
    dedupe = flag.get("kind", "") + ":" + (flag.get("exercise") or "session")
    c.execute(
        """INSERT INTO insights(created_at, workout_id, exercise_id, kind, severity,
                                title, detail, suggested_action, status, dedupe_key,
                                source, expires_on)
           VALUES(datetime('now'), ?, NULL, ?, ?, ?, ?, ?, 'open', ?, 'engine',
                  date('now', '+14 days'))
           ON CONFLICT(dedupe_key) WHERE status='open' AND dedupe_key IS NOT NULL DO UPDATE SET
             detail=excluded.detail, created_at=excluded.created_at""",
        (workout_id, flag.get("kind", "program"),
         flag.get("severity", "info"),
         flag.get("kind", "issue").replace("_", " ").title(),
         flag.get("detail", ""), flag.get("suggested_action"),
         dedupe),
    )


def get_open_insights(db: Database, limit: int = 20) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM insights WHERE status='open' ORDER BY "
        "CASE severity WHEN 'action' THEN 1 WHEN 'watch' THEN 2 ELSE 3 END, created_at DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_adjustments(db: Database, limit: int = 40) -> list[dict]:
    rows = db.execute(
        "SELECT a.*, e.name AS exercise_name, e.slug AS exercise_slug FROM next_session_adjustments a "
        "LEFT JOIN exercises e ON e.id=a.exercise_id "
        "WHERE a.status='pending' AND (a.applies_until IS NULL OR a.applies_until >= date('now')) "
        "ORDER BY a.created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["value"] = json.loads(d.get("value_json") or "{}")
        except Exception:
            d["value"] = {}
        out.append(d)
    return out


def recent_prs(db: Database, days: int = 30, limit: int = 20) -> list[dict]:
    rows = db.execute(
        "SELECT pr.*, e.name AS exercise_name, e.slug AS exercise_slug FROM personal_records pr "
        "JOIN exercises e ON e.id=pr.exercise_id "
        "WHERE pr.achieved_on >= date('now', ?) "
        "ORDER BY pr.achieved_on DESC LIMIT ?",
        (f"-{days} days", limit)
    ).fetchall()
    return [dict(r) for r in rows]
