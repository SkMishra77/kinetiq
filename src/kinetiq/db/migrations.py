"""Versioned SQL migrations applied at startup."""
from __future__ import annotations
import logging
import re
from pathlib import Path

from .connection import Database

log = logging.getLogger(__name__)

MIG_DIR = Path(__file__).parent / "migrations"
_FN_RE = re.compile(r"^(\d{4})_.*\.sql$")


def _discover() -> list[tuple[int, str, Path]]:
    out: list[tuple[int, str, Path]] = []
    for p in sorted(MIG_DIR.glob("*.sql")):
        m = _FN_RE.match(p.name)
        if not m:
            continue
        out.append((int(m.group(1)), p.stem, p))
    return out


def current_version(db: Database) -> int:
    try:
        row = db.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def apply_pending(db: Database) -> list[int]:
    """Apply any migrations whose version > current schema_migrations max.

    Returns the list of versions applied (empty if none)."""
    db.executescript(
        "CREATE TABLE IF NOT EXISTS schema_migrations("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);"
    )
    have = current_version(db)
    applied: list[int] = []
    for version, name, path in _discover():
        if version <= have:
            continue
        log.info("applying migration %s", name, extra={"event": "migrate_apply", "version": version})
        script = path.read_text(encoding="utf-8")
        # executescript() handles its own transaction and implicitly COMMITs
        # any pending one, so we can't wrap it in db.write(). Record success
        # in a separate write immediately after.
        db.executescript(script)
        db.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, datetime('now'))",
            (version, name),
        )
        applied.append(version)
    return applied
