"""Profile / equipment / preferences / injuries / limitations / body-metric SQL."""
from __future__ import annotations
import json
from typing import Any

from ..connection import Database


def get_profile(db: Database) -> dict | None:
    row = db.execute("SELECT * FROM profile WHERE id=1").fetchone()
    if not row:
        return None
    r = dict(row)
    for k in ("secondary_goals", "available_days"):
        r[k] = json.loads(r[k] or "[]")
    return r


def profile_snapshot(db: Database) -> dict:
    prof = get_profile(db) or {}
    prof["equipment"] = [dict(x) for x in db.execute("SELECT * FROM profile_equipment ORDER BY equipment").fetchall()]
    prof["preferences"] = [
        {**dict(x), "exercise_slug": None} for x in
        db.execute("""SELECT p.*, e.slug AS ex_slug, e.name AS ex_name
                      FROM exercise_preferences p JOIN exercises e ON e.id=p.exercise_id""").fetchall()
    ]
    prof["injuries"] = [
        {**dict(x),
         "affected_patterns": json.loads(x["affected_patterns"] or "[]"),
         "avoid_exercise_ids": json.loads(x["avoid_exercise_ids"] or "[]")}
        for x in db.execute("SELECT * FROM injuries ORDER BY created_at DESC").fetchall()
    ]
    prof["limitations"] = [
        {**dict(x), "affected_patterns": json.loads(x["affected_patterns"] or "[]")}
        for x in db.execute("SELECT * FROM limitations WHERE active=1").fetchall()
    ]
    latest = db.execute("SELECT * FROM body_metrics ORDER BY measured_on DESC, id DESC LIMIT 1").fetchone()
    prof["latest_body_metric"] = dict(latest) if latest else None
    return prof


REQUIRED_ONBOARDING_FIELDS = (
    "height_cm", "primary_goal", "training_experience", "days_per_week", "session_minutes",
)


def missing_onboarding(prof: dict) -> list[str]:
    m = []
    for f in REQUIRED_ONBOARDING_FIELDS:
        if prof.get(f) in (None, "", [], {}):
            m.append(f)
    if not prof.get("date_of_birth") and prof.get("age_years") in (None, 0):
        m.append("age_years")
    if not prof.get("equipment"):
        m.append("equipment")
    return m


def upsert_profile(db: Database, patch: dict, changed_fields: list[str], reason: str | None) -> dict:
    """Merge scalar fields into the singleton profile row.

    Callers are responsible for handling nested collections (equipment,
    preferences, injuries, limitations, body metrics).
    """
    with db.write() as c:
        row = c.execute("SELECT * FROM profile WHERE id=1").fetchone()
        if row is None:
            fields = {
                "id": 1,
                "display_name": patch.get("display_name"),
                "date_of_birth": patch.get("date_of_birth"),
                "age_years": patch.get("age_years"),
                "sex": patch.get("sex"),
                "height_cm": patch.get("height_cm"),
                "training_experience": patch.get("training_experience"),
                "training_years": patch.get("training_years"),
                "primary_goal": patch.get("primary_goal"),
                "secondary_goals": json.dumps(patch.get("secondary_goals") or []),
                "days_per_week": patch.get("days_per_week"),
                "available_days": json.dumps(patch.get("available_days") or []),
                "session_minutes": patch.get("session_minutes"),
                "gym_type": patch.get("gym_type"),
                "preferred_effort_scale": patch.get("preferred_effort_scale") or "rir",
                "timezone": patch.get("timezone"),
                "other_notes": patch.get("other_notes"),
                "created_at": None,
                "updated_at": None,
            }
            cols = ",".join(fields.keys())
            marks = ",".join(f":{k}" for k in fields.keys())
            sql = f"INSERT INTO profile({cols}) VALUES({marks})".replace(
                ":created_at", "datetime('now')").replace(":updated_at", "datetime('now')")
            del fields["created_at"]
            del fields["updated_at"]
            c.execute(sql, fields)
        else:
            updates: dict[str, Any] = {}
            for k, v in patch.items():
                if k not in {"secondary_goals", "available_days"} and v is not None:
                    updates[k] = v
            if patch.get("secondary_goals") is not None:
                updates["secondary_goals"] = json.dumps(patch["secondary_goals"])
            if patch.get("available_days") is not None:
                updates["available_days"] = json.dumps(patch["available_days"])
            if updates:
                sets = ",".join(f"{k}=:{k}" for k in updates)
                sets += ", updated_at=datetime('now')"
                c.execute(f"UPDATE profile SET {sets} WHERE id=1", updates)
        c.execute(
            "INSERT INTO profile_history(changed_at, changed_fields, snapshot_json, reason) "
            "VALUES(datetime('now'), ?, ?, ?)",
            (json.dumps(changed_fields), json.dumps(patch, default=str), reason),
        )
    return get_profile(db) or {}


def mark_onboarding_complete(db: Database) -> None:
    with db.write() as c:
        c.execute("UPDATE profile SET onboarding_completed_at=datetime('now'), updated_at=datetime('now') "
                  "WHERE id=1 AND onboarding_completed_at IS NULL")


def replace_equipment(db: Database, items: list[dict]) -> None:
    with db.write() as c:
        c.execute("DELETE FROM profile_equipment")
        for it in items:
            c.execute(
                "INSERT INTO profile_equipment(equipment, available, min_kg, max_kg, increment_kg, detail, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (it["equipment"], 1 if it.get("available", True) else 0,
                 it.get("min_kg"), it.get("max_kg"), it.get("increment_kg"), it.get("detail")),
            )


def replace_preferences(db: Database, likes: list[int] | None, dislikes: list[int] | None,
                         cannot: list[int] | None, avoid: list[int] | None) -> None:
    kinds: list[tuple[str, list[int] | None]] = [
        ("like", likes), ("dislike", dislikes), ("cannot", cannot), ("avoid", avoid),
    ]
    with db.write() as c:
        for kind, ids in kinds:
            if ids is None:
                continue
            c.execute("DELETE FROM exercise_preferences WHERE kind=?", (kind,))
            for eid in ids:
                c.execute(
                    "INSERT OR REPLACE INTO exercise_preferences(exercise_id, kind, created_at) "
                    "VALUES (?, ?, datetime('now'))",
                    (eid, kind),
                )


def replace_injuries(db: Database, items: list[dict]) -> None:
    with db.write() as c:
        c.execute("DELETE FROM injuries")
        for it in items:
            c.execute(
                """INSERT INTO injuries(body_region, description, status, side, onset_on,
                    affected_patterns, avoid_exercise_ids, notes, created_at, updated_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (
                    it["body_region"], it["description"], it.get("status", "active"),
                    it.get("side", "both"), it.get("onset_on"),
                    json.dumps(it.get("affected_patterns", [])),
                    json.dumps(it.get("avoid_exercise_ids", [])),
                    it.get("notes"),
                ),
            )


def replace_limitations(db: Database, items: list[dict]) -> None:
    with db.write() as c:
        c.execute("DELETE FROM limitations")
        for it in items:
            c.execute(
                "INSERT INTO limitations(description, kind, affected_patterns, active, created_at, updated_at) "
                "VALUES(?, ?, ?, 1, datetime('now'), datetime('now'))",
                (it["description"], it.get("kind", "other"),
                 json.dumps(it.get("affected_patterns", []))),
            )


def add_body_metric(db: Database, measured_on: str, weight_kg: float | None,
                     body_fat_pct: float | None, source: str,
                     measurements: dict | None, notes: str | None) -> int:
    with db.write() as c:
        cur = c.execute(
            "INSERT INTO body_metrics(measured_on, weight_kg, body_fat_pct, source, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (measured_on, weight_kg, body_fat_pct, source, notes),
        )
        mid = cur.lastrowid
        for site, val in (measurements or {}).items():
            if val is None:
                continue
            try:
                c.execute(
                    "INSERT INTO body_measurements(metric_id, site, value_cm) VALUES(?, ?, ?)",
                    (mid, site, float(val)),
                )
            except Exception:
                pass
        return mid


def latest_bodyweight(db: Database) -> float | None:
    row = db.execute(
        "SELECT weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL "
        "ORDER BY measured_on DESC, id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None
