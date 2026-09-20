"""Daily check-in repo."""
from __future__ import annotations
import json

from ..connection import Database


def upsert_checkin(db: Database, *, checkin_on: str, bodyweight_kg: float | None,
                    sleep_hours: float | None, sleep_quality: int | None,
                    energy: int | None, soreness: dict | None,
                    stress: int | None, resting_hr: int | None,
                    notes: str | None) -> int:
    with db.write() as c:
        row = c.execute("SELECT id FROM checkins WHERE checkin_on=?", (checkin_on,)).fetchone()
        if row:
            c.execute(
                """UPDATE checkins SET
                     bodyweight_kg=COALESCE(?, bodyweight_kg),
                     sleep_hours=COALESCE(?, sleep_hours),
                     sleep_quality=COALESCE(?, sleep_quality),
                     energy=COALESCE(?, energy),
                     soreness_json=COALESCE(?, soreness_json),
                     stress=COALESCE(?, stress),
                     resting_hr=COALESCE(?, resting_hr),
                     notes=COALESCE(?, notes),
                     updated_at=datetime('now')
                   WHERE id=?""",
                (bodyweight_kg, sleep_hours, sleep_quality, energy,
                 json.dumps(soreness) if soreness is not None else None,
                 stress, resting_hr, notes, row[0]),
            )
            return row[0]
        cur = c.execute(
            """INSERT INTO checkins(checkin_on, bodyweight_kg, sleep_hours, sleep_quality,
                    energy, soreness_json, stress, resting_hr, notes,
                    created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (checkin_on, bodyweight_kg, sleep_hours, sleep_quality, energy,
             json.dumps(soreness or {}), stress, resting_hr, notes),
        )
        return cur.lastrowid


def latest_readiness(db: Database, days: int = 3) -> dict:
    rows = db.execute(
        "SELECT * FROM checkins WHERE checkin_on >= date('now', ?) ORDER BY checkin_on DESC",
        (f"-{days} days",)
    ).fetchall()
    out = {"count": len(rows)}
    if rows:
        latest = dict(rows[0])
        out.update({
            "sleep_hours": latest["sleep_hours"],
            "energy": latest["energy"],
            "checkin_on": latest["checkin_on"],
        })
        vals = [r["sleep_hours"] for r in rows if r["sleep_hours"] is not None]
        if vals:
            out["sleep_hours_avg"] = round(sum(vals) / len(vals), 2)
    return out


def bodyweight_trend(db: Database) -> dict:
    row_latest = db.execute(
        "SELECT checkin_on, bodyweight_kg FROM checkins WHERE bodyweight_kg IS NOT NULL "
        "ORDER BY checkin_on DESC LIMIT 1"
    ).fetchone()
    if not row_latest:
        return {"latest": None}
    rows_7 = db.execute(
        "SELECT AVG(bodyweight_kg) FROM checkins "
        "WHERE bodyweight_kg IS NOT NULL AND checkin_on >= date('now','-7 days')"
    ).fetchone()
    rows_28 = db.execute(
        "SELECT AVG(bodyweight_kg) FROM checkins "
        "WHERE bodyweight_kg IS NOT NULL AND checkin_on >= date('now','-28 days')"
    ).fetchone()
    return {
        "latest": row_latest["bodyweight_kg"],
        "as_of": row_latest["checkin_on"],
        "avg_7d": rows_7[0],
        "avg_28d": rows_28[0],
    }
