"""Alias resolution — checks normalisation and fuzzy fallback thresholds."""
import pytest

from kinetiq.parsing.aliases import normalise, resolve


def test_normalise_expands_abbreviations():
    assert normalise("DB press") == "dumbbell press"
    assert normalise("BB row") == "barbell row"
    assert normalise("OHP") == "overhead press"
    assert normalise("Bench") == "bench press"
    assert normalise("bench press") == "bench press"


def _fixture_pool():
    pool = [
        (1, "bench-press", "Bench Press"),
        (2, "dumbbell-bench-press", "Dumbbell Bench Press"),
        (3, "lat-pulldown", "Lat Pulldown"),
        (4, "incline-dumbbell-press", "Incline Dumbbell Press"),
    ]
    alias_map = {normalise(name): (i, slug, name) for i, slug, name in pool}
    # Add a few aliases from the seed
    alias_map[normalise("lat pd")] = (3, "lat-pulldown", "Lat Pulldown")
    return alias_map, pool


def test_alias_exact_match():
    alias_map, pool = _fixture_pool()
    r = resolve("Bench Press", alias_map=alias_map, name_pool=pool)
    assert r.exercise_id == 1
    assert r.matched_on == "alias"


def test_alias_via_abbreviation_expansion():
    alias_map, pool = _fixture_pool()
    r = resolve("lat pd", alias_map=alias_map, name_pool=pool)
    assert r.exercise_id == 3


def test_fuzzy_low_score_returns_none_with_candidates():
    alias_map, pool = _fixture_pool()
    r = resolve("bicep curl", alias_map=alias_map, name_pool=pool)
    assert r.exercise_id is None
    assert r.candidates
