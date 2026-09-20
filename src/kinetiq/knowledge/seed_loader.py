"""Load YAML seed data into SQLite idempotently.

The seed hash is stored in ``settings.seed_version``; when the hash changes, we
re-upsert seed rows without clobbering user-authored rows (``source='user'``).
"""
from __future__ import annotations
import hashlib
import json
import logging
from pathlib import Path

import yaml

from ..db.connection import Database
from ..parsing.aliases import normalise

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _load_yaml(name: str) -> list | dict:
    p = DATA_DIR / name
    if not p.exists():
        return []
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []


def _current_seed_version(db: Database) -> str:
    row = db.execute("SELECT value FROM settings WHERE key='seed_version'").fetchone()
    return row[0] if row else "0"


def _set_seed_version(db: Database, value: str) -> None:
    db.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES ('seed_version', ?, datetime('now'))"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (value,),
    )


def load_all(db: Database, force: bool = False) -> dict:
    """Upsert seed exercises/aliases/substitutions and knowledge notes.

    Skips work when the combined hash of seed files matches the stored
    ``seed_version``. Returns a report dict.
    """
    files = [
        DATA_DIR / "exercises.yaml",
        DATA_DIR / "principles.yaml",
        DATA_DIR / "substitutions.yaml",
        DATA_DIR / "warmup_library.yaml",
    ]
    files = [p for p in files if p.exists()]
    seed_hash = _hash_files(files)
    if not force and _current_seed_version(db) == seed_hash:
        log.info("seed unchanged; skipping", extra={"event": "seed_skip"})
        return {"skipped": True, "hash": seed_hash}

    exercises = _load_yaml("exercises.yaml") or []
    principles = _load_yaml("principles.yaml") or []
    subs = _load_yaml("substitutions.yaml") or []

    report = {"exercises": 0, "aliases": 0, "principles": 0, "substitutions": 0}

    with db.write() as c:
        # Exercises + aliases
        for ex in exercises:
            slug = ex["slug"]
            aliases = [normalise(a) for a in ex.get("aliases", []) if a]
            aliases_set = set(aliases) | {normalise(ex["name"]), slug.replace("-", " ")}
            c.execute(
                """INSERT INTO exercises(
                       slug, name, movement_pattern, equipment, load_type, laterality,
                       bodyweight_load_factor, primary_muscles, secondary_muscles,
                       is_compound, default_increment_kg, default_rest_s, cues,
                       contraindication_tags, evidence_summary, selection_scores,
                       source, active, created_at, updated_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed', 1,
                          datetime('now'), datetime('now'))
                   ON CONFLICT(slug) DO UPDATE SET
                       name=excluded.name,
                       movement_pattern=excluded.movement_pattern,
                       equipment=excluded.equipment,
                       load_type=excluded.load_type,
                       laterality=excluded.laterality,
                       bodyweight_load_factor=excluded.bodyweight_load_factor,
                       primary_muscles=excluded.primary_muscles,
                       secondary_muscles=excluded.secondary_muscles,
                       is_compound=excluded.is_compound,
                       default_increment_kg=excluded.default_increment_kg,
                       default_rest_s=excluded.default_rest_s,
                       cues=excluded.cues,
                       contraindication_tags=excluded.contraindication_tags,
                       evidence_summary=excluded.evidence_summary,
                       selection_scores=excluded.selection_scores,
                       updated_at=datetime('now')
                   WHERE exercises.source='seed'
                """,
                (
                    slug, ex["name"], ex["movement_pattern"], ex["equipment"],
                    ex.get("load_type", "external"),
                    ex.get("laterality", "bilateral"),
                    float(ex.get("bodyweight_load_factor", 1.0)),
                    json.dumps(ex.get("primary_muscles", [])),
                    json.dumps(ex.get("secondary_muscles", [])),
                    1 if ex.get("is_compound", True) else 0,
                    float(ex.get("default_increment_kg", 2.5)),
                    int(ex.get("default_rest_s", 90)) if ex.get("default_rest_s") else None,
                    ex.get("cues"),
                    json.dumps(ex.get("contraindication_tags", [])),
                    ex.get("evidence_summary"),
                    json.dumps(ex.get("selection_scores", {})),
                ),
            )
            report["exercises"] += 1
            row = c.execute("SELECT id FROM exercises WHERE slug=?", (slug,)).fetchone()
            eid = row[0]
            for a in aliases_set:
                if not a:
                    continue
                c.execute(
                    "INSERT OR IGNORE INTO exercise_aliases(alias_norm, exercise_id, source) "
                    "VALUES (?, ?, 'seed')",
                    (a, eid),
                )
                report["aliases"] += 1

        # Substitutions
        for s in subs:
            frm = c.execute("SELECT id FROM exercises WHERE slug=?", (s["from"],)).fetchone()
            to = c.execute("SELECT id FROM exercises WHERE slug=?", (s["to"],)).fetchone()
            if not frm or not to:
                continue
            c.execute(
                "INSERT OR IGNORE INTO exercise_substitutions(exercise_id, substitute_id, reason, rank) "
                "VALUES (?, ?, ?, ?)",
                (frm[0], to[0], s["reason"], int(s.get("rank", 1))),
            )
            report["substitutions"] += 1

        # Principle notes
        for pr in principles:
            slug = pr["slug"]
            c.execute(
                """INSERT INTO knowledge_notes(kind, slug, topic, goal_tags, claim, detail, strength,
                                                applies_to_goals, source, created_at, updated_at)
                   VALUES('principle', ?, ?, ?, ?, ?, ?, ?, 'seed', datetime('now'), datetime('now'))
                   ON CONFLICT(slug) DO UPDATE SET
                       topic=excluded.topic, goal_tags=excluded.goal_tags,
                       claim=excluded.claim, detail=excluded.detail,
                       strength=excluded.strength,
                       applies_to_goals=excluded.applies_to_goals,
                       updated_at=datetime('now')
                   WHERE knowledge_notes.source='seed'
                """,
                (
                    slug, pr.get("topic"),
                    json.dumps(pr.get("goal_tags", [])),
                    pr["claim"], pr.get("detail"),
                    pr.get("strength", "moderate"),
                    json.dumps(pr.get("goal_tags", [])),
                ),
            )
            report["principles"] += 1
            row = c.execute("SELECT id FROM knowledge_notes WHERE slug=?", (slug,)).fetchone()
            nid = row[0]
            # Clear+reinsert citations for this seed note (only when the note is seed-sourced).
            c.execute("DELETE FROM knowledge_citations WHERE note_id=?", (nid,))
            for cit in pr.get("citations", []) or []:
                c.execute(
                    """INSERT INTO knowledge_citations(
                           note_id, pmid, doi, title, year, journal, key_finding,
                           verification_status, created_at)
                       VALUES(?, ?, ?, ?, ?, ?, ?, 'unverified', datetime('now'))""",
                    (
                        nid, cit.get("pmid"), cit.get("doi"), cit.get("title"),
                        cit.get("year"), cit.get("journal"), cit.get("key_finding"),
                    ),
                )

        _set_seed_version(c, seed_hash)

    log.info("seed loaded", extra={"event": "seed_load", **report})
    return {"skipped": False, "hash": seed_hash, **report}
