"""Issue repo (pain/injury/limitation runtime state)."""
from __future__ import annotations
import json

from ..connection import Database


def open_issues(db: Database) -> list[dict]:
    rows = db.execute("SELECT * FROM issues WHERE status IN ('open','monitoring') "
                      "ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["restrictions"] = json.loads(d["restrictions_json"] or "{}")
        except Exception:
            d["restrictions"] = {}
        out.append(d)
    return out


def open_issue(db: Database, *, kind: str, body_region: str, side: str,
                 severity: int, description: str, restrictions: dict | None,
                 linked_exercise_id: int | None, source: str = "report") -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO issues(kind, body_region, side, severity, description,
                    onset_on, status, restrictions_json, source, linked_exercise_id,
                    created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, date('now'), 'open', ?, ?, ?, datetime('now'), datetime('now'))""",
            (kind, body_region, side, severity, description,
             json.dumps(restrictions or {}), source, linked_exercise_id),
        )
        return cur.lastrowid


def update_issue(db: Database, issue_id: int, *, status: str | None = None,
                  severity: int | None = None, restrictions: dict | None = None,
                  description: str | None = None) -> None:
    sets = []
    args = []
    if status is not None:
        sets.append("status=?")
        args.append(status)
        if status == "resolved":
            sets.append("resolved_at=datetime('now')")
    if severity is not None:
        sets.append("severity=?")
        args.append(severity)
    if restrictions is not None:
        sets.append("restrictions_json=?")
        args.append(json.dumps(restrictions))
    if description is not None:
        sets.append("description=?")
        args.append(description)
    if not sets:
        return
    sets.append("updated_at=datetime('now')")
    args.append(issue_id)
    with db.write() as c:
        c.execute(f"UPDATE issues SET {', '.join(sets)} WHERE id=?", tuple(args))
