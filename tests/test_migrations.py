"""Migration idempotency + seed round-trip."""
from kinetiq.db.migrations import apply_pending, current_version
from kinetiq.knowledge.seed_loader import load_all


def test_migration_idempotent(fresh_db):
    # Already applied by fixture
    v = current_version(fresh_db)
    assert v >= 1
    again = apply_pending(fresh_db)
    assert again == []


def test_seed_hash_short_circuits(fresh_db):
    r1 = load_all(fresh_db)
    r2 = load_all(fresh_db)
    assert r1.get("skipped") is False
    assert r2.get("skipped") is True


def test_seed_creates_exercises_and_aliases(seeded_db):
    n = seeded_db.execute("SELECT COUNT(*) FROM exercises WHERE source='seed'").fetchone()[0]
    assert n >= 30
    a = seeded_db.execute("SELECT COUNT(*) FROM exercise_aliases").fetchone()[0]
    assert a >= 50
    p = seeded_db.execute("SELECT COUNT(*) FROM knowledge_notes WHERE kind='principle'").fetchone()[0]
    assert p >= 10
