"""Knowledge notes + research cache SQL."""
from __future__ import annotations
import json

from ..connection import Database


def search_notes(db: Database, *, query: str | None = None, topic: str | None = None,
                  exercise_id: int | None = None, goal: str | None = None,
                  include_unverified: bool = False, limit: int = 15) -> list[dict]:
    sql = "SELECT * FROM knowledge_notes WHERE deleted_at IS NULL"
    args: list = []
    if query:
        sql += " AND (claim LIKE ? OR detail LIKE ?)"
        args += [f"%{query}%", f"%{query}%"]
    if topic:
        sql += " AND topic=?"
        args.append(topic)
    if exercise_id:
        sql += " AND (exercise_id=? OR exercise_id IS NULL)"
        args.append(exercise_id)
    if goal:
        sql += " AND (goal_tags LIKE ? OR goal_tags='[]')"
        args.append(f'%"{goal}"%')
    sql += " ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)
    rows = db.execute(sql, tuple(args)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("goal_tags", "muscle_tags", "applies_to_goals"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except Exception:
                d[k] = []
        cites = db.execute(
            "SELECT * FROM knowledge_citations WHERE note_id=? " +
            ("" if include_unverified else "AND verification_status='verified'"),
            (r["id"],)
        ).fetchall()
        d["citations"] = [dict(c) for c in cites]
        out.append(d)
    return out


def save_finding(db: Database, *, claim: str, detail: str | None, strength: str,
                  topic: str | None, exercise_id: int | None,
                  goal_tags: list[str], muscle_tags: list[str],
                  citations: list[dict]) -> int:
    with db.write() as c:
        cur = c.execute(
            """INSERT INTO knowledge_notes(kind, topic, exercise_id, goal_tags, muscle_tags,
                        claim, detail, strength, applies_to_goals, source,
                        created_at, updated_at)
               VALUES('finding', ?, ?, ?, ?, ?, ?, ?, ?, 'curated',
                        datetime('now'), datetime('now'))""",
            (topic, exercise_id, json.dumps(goal_tags), json.dumps(muscle_tags),
             claim, detail, strength, json.dumps(goal_tags)),
        )
        nid = cur.lastrowid
        for cit in citations:
            c.execute(
                """INSERT INTO knowledge_citations(note_id, pmid, doi, title, year,
                            journal, key_finding, verification_status, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, 'unverified', datetime('now'))""",
                (nid, cit.get("pmid"), cit.get("doi"), cit.get("title"),
                 cit.get("year"), cit.get("journal"), cit.get("key_finding")),
            )
        return nid


def get_cached(db: Database, provider: str, query_hash: str) -> dict | None:
    r = db.execute(
        "SELECT * FROM research_cache WHERE provider=? AND query_hash=? "
        "AND expires_at >= datetime('now')",
        (provider, query_hash)
    ).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["response"] = json.loads(d["response_json"])
    except Exception:
        d["response"] = None
    return d


def set_cached(db: Database, provider: str, query_hash: str, query_text: str,
                params: dict, response: dict, http_status: int, ttl_days: int = 30) -> None:
    with db.write() as c:
        c.execute(
            """INSERT INTO research_cache(provider, query_hash, query_text, params_json,
                    response_json, http_status, fetched_at, expires_at)
               VALUES(?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', ?))
               ON CONFLICT(query_hash) DO UPDATE SET
                    query_text=excluded.query_text, params_json=excluded.params_json,
                    response_json=excluded.response_json, http_status=excluded.http_status,
                    fetched_at=excluded.fetched_at, expires_at=excluded.expires_at""",
            (provider, query_hash, query_text, json.dumps(params),
             json.dumps(response), http_status, f"+{ttl_days} days"),
        )
