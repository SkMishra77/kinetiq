"""Exercise library repo."""
from __future__ import annotations

import json
from typing import Any

from ...parsing.aliases import Resolution, normalise, resolve
from ..connection import Database


def all_exercises(db: Database, include_deleted: bool = False) -> list[dict]:
    where = "" if include_deleted else " WHERE active=1"
    rows = db.execute("SELECT * FROM exercises" + where + " ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(db: Database, exercise_id: int) -> dict | None:
    r = db.execute("SELECT * FROM exercises WHERE id=?", (exercise_id,)).fetchone()
    return _row_to_dict(r) if r else None


def get_by_slug(db: Database, slug: str) -> dict | None:
    r = db.execute("SELECT * FROM exercises WHERE slug=?", (slug,)).fetchone()
    return _row_to_dict(r) if r else None


def _row_to_dict(r: Any) -> dict:
    d = dict(r)
    for k in ("primary_muscles", "secondary_muscles", "contraindication_tags", "selection_scores"):
        try:
            d[k] = json.loads(d.get(k) or "[]" if k != "selection_scores" else d.get(k) or "{}")
        except Exception:
            d[k] = [] if k != "selection_scores" else {}
    return d


def resolve_name(db: Database, raw: str) -> Resolution:
    alias_rows = db.execute(
        "SELECT a.alias_norm, e.id, e.slug, e.name FROM exercise_aliases a "
        "JOIN exercises e ON e.id=a.exercise_id WHERE e.active=1"
    ).fetchall()
    alias_map = {r["alias_norm"]: (r["id"], r["slug"], r["name"]) for r in alias_rows}
    pool = [(r["id"], r["slug"], r["name"]) for r in db.execute(
        "SELECT id, slug, name FROM exercises WHERE active=1").fetchall()]
    return resolve(raw, alias_map=alias_map, name_pool=pool)


def create_exercise(db: Database, *, name: str, movement_pattern: str, equipment: str,
                     load_type: str = "external", laterality: str = "bilateral",
                     primary_muscles: list[str] | None = None,
                     secondary_muscles: list[str] | None = None,
                     is_compound: bool = True,
                     default_increment_kg: float = 2.5,
                     cues: str | None = None,
                     contraindication_tags: list[str] | None = None,
                     source: str = "user",
                     aliases: list[str] | None = None) -> dict:
    slug = _slugify(name)
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO exercises(slug, name, movement_pattern, equipment, load_type, laterality,
                bodyweight_load_factor, primary_muscles, secondary_muscles, is_compound,
                default_increment_kg, cues, contraindication_tags, source, active,
                created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?, 1,
                      datetime('now'), datetime('now'))""",
            (slug, name, movement_pattern, equipment, load_type, laterality,
             json.dumps(primary_muscles or []), json.dumps(secondary_muscles or []),
             1 if is_compound else 0, default_increment_kg, cues,
             json.dumps(contraindication_tags or []), source),
        )
        eid = cur.lastrowid
        for a in ((aliases or []) + [name]):
            n = normalise(a)
            if n:
                c.execute("INSERT OR IGNORE INTO exercise_aliases(alias_norm, exercise_id, source) "
                          "VALUES (?, ?, ?)", (n, eid, source))
    return get_by_id(db, eid)  # type: ignore[return-value]


def add_alias(db: Database, exercise_id: int, alias: str) -> None:
    n = normalise(alias)
    if not n:
        return
    with db.write() as c:
        c.execute("INSERT OR IGNORE INTO exercise_aliases(alias_norm, exercise_id, source) "
                  "VALUES (?, ?, 'user')", (n, exercise_id))


def _slugify(name: str) -> str:
    import re
    s = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


def substitutes_for(db: Database, exercise_id: int, reason: str | None = None,
                     limit: int = 5) -> list[dict]:
    args: list[Any] = [exercise_id]
    where = "s.exercise_id=?"
    if reason:
        where += " AND s.reason=?"
        args.append(reason)
    rows = db.execute(
        f"""SELECT s.reason, s.rank, e.id, e.slug, e.name FROM exercise_substitutions s
             JOIN exercises e ON e.id=s.substitute_id
             WHERE {where}
             ORDER BY s.rank ASC LIMIT ?""",
        (*args, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def search(db: Database, *, query: str | None = None, muscle: str | None = None,
           equipment: list[str] | None = None, movement_pattern: str | None = None,
           limit: int = 15) -> list[dict]:
    sql = "SELECT * FROM exercises WHERE active=1"
    args: list[Any] = []
    if query:
        sql += " AND (name LIKE ? OR slug LIKE ?)"
        args += [f"%{query}%", f"%{query}%"]
    if movement_pattern:
        sql += " AND movement_pattern=?"
        args.append(movement_pattern)
    if muscle:
        sql += " AND (primary_muscles LIKE ? OR secondary_muscles LIKE ?)"
        args += [f'%"{muscle}"%', f'%"{muscle}"%']
    if equipment:
        placeholders = ",".join("?" for _ in equipment)
        sql += f" AND equipment IN ({placeholders})"
        args += list(equipment)
    sql += " ORDER BY name LIMIT ?"
    args.append(limit)
    return [_row_to_dict(r) for r in db.execute(sql, tuple(args)).fetchall()]
