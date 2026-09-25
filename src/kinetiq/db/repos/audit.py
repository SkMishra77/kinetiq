"""Audit log writes."""
from __future__ import annotations

import json

from ..connection import Database


def record(db: Database, *, tool_name: str, args_preview: dict | None,
            ok: bool, error_class: str | None, duration_ms: int) -> None:
    try:
        with db.write() as c:
            c.execute(
                "INSERT INTO audit_log(at, tool_name, args_preview, ok, error_class, duration_ms) "
                "VALUES(datetime('now'), ?, ?, ?, ?, ?)",
                (tool_name, json.dumps(args_preview or {}, default=str)[:2000],
                 1 if ok else 0, error_class, duration_ms),
            )
    except Exception:
        # Never fail a request because auditing failed.
        pass
