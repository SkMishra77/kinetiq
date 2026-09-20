"""Double-progression rule table tests."""
from kinetiq.engine.progression import decide_double_progression, SetSummary


def _sets(load, reps, n=3, rpe=None, rir=None):
    return [SetSummary(load_kg=load, reps=reps, rpe=rpe, rir=rir) for _ in range(n)]


def test_hits_rep_max_increases_load():
    dec = decide_double_progression(
        _sets(60, 10, n=3, rir=2), rep_min=6, rep_max=10, target_rir=2,
        increment_kg=2.5, movement_pattern="horizontal_push",
    )
    assert dec.next_action == "increase_load"
    assert dec.next_load_kg == 62.5
    assert dec.next_rep_target == 6


def test_hits_rep_min_holds_and_adds_reps():
    dec = decide_double_progression(
        _sets(60, 8, n=3), rep_min=6, rep_max=10, target_rir=2,
        increment_kg=2.5, movement_pattern="horizontal_push",
    )
    assert dec.next_action == "add_reps"
    assert dec.next_load_kg == 60.0
    assert dec.next_rep_target == 9


def test_below_rep_min_reduces():
    dec = decide_double_progression(
        [SetSummary(load_kg=60, reps=5), SetSummary(load_kg=60, reps=4), SetSummary(load_kg=60, reps=3)],
        rep_min=6, rep_max=10, target_rir=2, increment_kg=2.5,
        movement_pattern="horizontal_push",
    )
    assert dec.next_action == "reduce_load"
    assert dec.next_load_kg is not None
    assert dec.next_load_kg < 60.0


def test_lower_body_uses_larger_percent_step():
    # Squat @ 100 kg × 8 (all rep_max) → +5% not +2.5%
    dec = decide_double_progression(
        _sets(100, 8, n=3, rir=2), rep_min=5, rep_max=8, target_rir=2,
        increment_kg=2.5, movement_pattern="squat",
    )
    assert dec.next_action == "increase_load"
    # 5% of 100 = 5 kg, round to 2.5-kg step → 105.0
    assert dec.next_load_kg == 105.0
