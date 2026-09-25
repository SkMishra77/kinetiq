"""Cardio / conditioning session repo."""
from __future__ import annotations

from ..connection import Database


def log_cardio(
    db: Database,
    *,
    performed_on: str,
    activity: str,
    duration_min: int | None = None,
    distance_km: float | None = None,
    avg_hr: int | None = None,
    max_hr: int | None = None,
    zone: str | None = None,
    intensity: str | None = None,
    calories_est: int | None = None,
    notes: str | None = None,
    workout_id: int | None = None,
) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO cardio_sessions(
                    performed_on, activity, duration_min, distance_km,
                    avg_hr, max_hr, zone, intensity, calories_est, notes,
                    workout_id, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (performed_on, activity, duration_min, distance_km,
             avg_hr, max_hr, zone, intensity, calories_est, notes, workout_id),
        )
        return cur.lastrowid


def cardio_history(db: Database, since: str | None = None, limit: int = 20) -> list[dict]:
    if since:
        rows = db.execute(
            "SELECT * FROM cardio_sessions WHERE performed_on >= ? "
            "ORDER BY performed_on DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM cardio_sessions ORDER BY performed_on DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def weekly_cardio_summary(db: Database) -> dict:
    """Summarise last 7 days of cardio."""
    rows = db.execute(
        "SELECT activity, SUM(duration_min) AS total_min, COUNT(*) AS sessions, "
        "SUM(distance_km) AS total_km "
        "FROM cardio_sessions WHERE performed_on >= date('now','-7 days') "
        "GROUP BY activity ORDER BY total_min DESC",
    ).fetchall()
    total = db.execute(
        "SELECT SUM(duration_min), COUNT(*) FROM cardio_sessions "
        "WHERE performed_on >= date('now','-7 days')",
    ).fetchone()
    return {
        "by_activity": [dict(r) for r in rows],
        "total_minutes": total[0] or 0,
        "total_sessions": total[1] or 0,
    }
