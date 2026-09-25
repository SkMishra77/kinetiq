"""Program / block / session_template / template_exercise SQL."""
from __future__ import annotations

import json
from typing import Any

from ..connection import Database


def get_active(db: Database) -> dict | None:
    r = db.execute("SELECT * FROM programs WHERE status='active'").fetchone()
    if not r:
        return None
    return _row(r)


def _row(r: Any) -> dict:
    d = dict(r)
    for k in ("deload_policy",):
        if k in d:
            try:
                d[k] = json.loads(d[k] or "{}")
            except Exception:
                d[k] = {}
    return d


def archive_active(db: Database, reason: str | None = None) -> int | None:
    with db.write() as c:
        row = c.execute("SELECT id FROM programs WHERE status='active'").fetchone()
        if not row:
            return None
        pid = row[0]
        c.execute("UPDATE programs SET status='archived', archived_at=datetime('now'), "
                  "updated_at=datetime('now'), notes=COALESCE(notes,'') || CASE WHEN ? IS NULL THEN '' "
                  "ELSE (' | archived: ' || ?) END WHERE id=?",
                  (reason, reason, pid))
        return pid


def create_program(db: Database, *, name: str, goal: str, split_type: str,
                    days_per_week: int, progression_model: str = "double_progression",
                    block_length_weeks: int = 4, deload_policy: dict | None = None,
                    rationale: str | None = None, activate: bool = True) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO programs(name, goal, split_type, days_per_week, progression_model,
                                    block_length_weeks, deload_policy, rationale,
                                    status, started_on, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), datetime('now'), datetime('now'))""",
            (name, goal, split_type, days_per_week, progression_model,
             block_length_weeks, json.dumps(deload_policy or {}),
             rationale, "active" if activate else "draft"),
        )
        pid = cur.lastrowid
        # First block (accumulation) auto-created
        c.execute(
            """INSERT INTO program_blocks(program_id, block_no, kind, planned_weeks,
                    volume_multiplier, load_multiplier, rir_offset, status, started_on)
               VALUES(?, 1, 'accumulation', ?, 1.0, 1.0, 0, 'active', date('now'))""",
            (pid, block_length_weeks),
        )
        return pid


def add_session_template(db: Database, program_id: int, order_no: int, *,
                          name: str, key_name: str | None = None,
                          focus: str | None = None,
                          target_muscles: list[str] | None = None,
                          est_minutes: int | None = None) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO session_templates(program_id, order_no, key_name, name, focus,
                                              target_muscles, est_minutes)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (program_id, order_no, key_name, name, focus,
             json.dumps(target_muscles or []), est_minutes),
        )
        return cur.lastrowid


def add_template_exercise(db: Database, template_id: int, order_no: int, *,
                           exercise_id: int, sets: int, rep_min: int, rep_max: int,
                           target_rir: int = 2, rest_s: int = 120,
                           tempo: str | None = None, role: str = "primary",
                           progression_rule: str | None = None,
                           increment_kg: float | None = None,
                           start_weight_kg: float | None = None,
                           is_optional: bool = False, notes: str | None = None) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO template_exercises(template_id, order_no, exercise_id, sets,
                        rep_min, rep_max, target_rir, rest_s, tempo, role, progression_rule,
                        increment_kg, start_weight_kg, is_optional, notes, active, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))""",
            (template_id, order_no, exercise_id, sets, rep_min, rep_max,
             target_rir, rest_s, tempo, role, progression_rule,
             increment_kg, start_weight_kg, 1 if is_optional else 0, notes),
        )
        return cur.lastrowid


def program_with_templates(db: Database, program_id: int | None = None) -> dict | None:
    if program_id is None:
        p = get_active(db)
    else:
        r = db.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
        p = _row(r) if r else None
    if not p:
        return None
    templates = [dict(t) for t in db.execute(
        "SELECT * FROM session_templates WHERE program_id=? ORDER BY order_no",
        (p["id"],)
    ).fetchall()]
    for t in templates:
        t["target_muscles"] = json.loads(t["target_muscles"] or "[]")
        t["exercises"] = [dict(x) for x in db.execute(
            "SELECT te.*, e.slug AS exercise_slug, e.name AS exercise_name, "
            "       e.movement_pattern, e.equipment, e.primary_muscles, e.secondary_muscles, "
            "       e.default_increment_kg AS ex_default_increment "
            "FROM template_exercises te JOIN exercises e ON e.id=te.exercise_id "
            "WHERE te.template_id=? AND te.active=1 ORDER BY te.order_no",
            (t["id"],)
        ).fetchall()]
        for te in t["exercises"]:
            te["primary_muscles"] = json.loads(te["primary_muscles"] or "[]")
            te["secondary_muscles"] = json.loads(te["secondary_muscles"] or "[]")
    p["templates"] = templates
    # active block
    b = db.execute("SELECT * FROM program_blocks WHERE program_id=? AND status='active'",
                   (p["id"],)).fetchone()
    p["active_block"] = dict(b) if b else None
    return p


def advance_rotation(db: Database, program_id: int) -> int:
    """Advance the rotation pointer by 1 (wrapping)."""
    with db.write() as c:
        row = c.execute("SELECT next_template_index FROM programs WHERE id=?",
                        (program_id,)).fetchone()
        if not row:
            return 0
        n = c.execute("SELECT COUNT(*) FROM session_templates WHERE program_id=?",
                      (program_id,)).fetchone()[0] or 1
        nxt = (row[0] + 1) % n
        c.execute("UPDATE programs SET next_template_index=?, updated_at=datetime('now') "
                  "WHERE id=?", (nxt, program_id))
        return nxt


def set_next_index(db: Database, program_id: int, idx: int) -> None:
    with db.write() as c:
        c.execute("UPDATE programs SET next_template_index=?, updated_at=datetime('now') "
                  "WHERE id=?", (idx, program_id))
