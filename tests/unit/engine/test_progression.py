"""Double-progression rule table tests."""
from kinetiq.engine.progression import SetSummary, decide_double_progression


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


# ---- RPE-autoregulated progression tests --------------------------------

from kinetiq.engine.progression import decide_rpe_autoregulated


def _rpe_sets(load, reps, n=3, rpe=7.0):
    return [SetSummary(load_kg=load, reps=reps, rpe=rpe) for _ in range(n)]


def test_rpe_auto_below_target_increases():
    dec = decide_rpe_autoregulated(
        _rpe_sets(80, 8, rpe=7.0), target_rpe=8.0,
        increment_kg=2.5, movement_pattern="horizontal_push",
    )
    assert dec.next_action == "increase_load"
    assert dec.next_load_kg > 80.0


def test_rpe_auto_at_target_increases():
    dec = decide_rpe_autoregulated(
        _rpe_sets(80, 8, rpe=8.0), target_rpe=8.0,
        increment_kg=2.5, rep_min=6, rep_max=12,
    )
    assert dec.next_action == "increase_load"


def test_rpe_auto_over_target_holds():
    dec = decide_rpe_autoregulated(
        _rpe_sets(80, 8, rpe=9.5), target_rpe=8.0,
        increment_kg=2.5,
    )
    assert dec.next_action == "hold"


def test_rpe_auto_very_high_rpe_below_min_reduces():
    sets = [SetSummary(load_kg=80, reps=3, rpe=9.5)]
    dec = decide_rpe_autoregulated(
        sets, target_rpe=8.0, increment_kg=2.5, rep_min=6,
    )
    assert dec.next_action == "reduce_load"
    assert dec.next_load_kg < 80.0


def test_rpe_auto_no_rpe_falls_back_to_double():
    sets = [SetSummary(load_kg=80, reps=10) for _ in range(3)]
    dec = decide_rpe_autoregulated(
        sets, target_rpe=8.0, increment_kg=2.5, rep_min=6, rep_max=10,
    )
    assert dec.next_action == "increase_load"


# ---- Wave progression tests ------------------------------------------------

from kinetiq.engine.progression import decide_wave


def test_wave_phase1_hit_all_advances():
    dec = decide_wave(
        _sets(60, 10, n=3), week_in_block=1, increment_kg=2.5,
    )
    assert dec.next_action == "increase_load"
    assert dec.next_rep_target == 8


def test_wave_phase2_hit_all_advances():
    dec = decide_wave(
        _sets(62.5, 8, n=3), week_in_block=2, increment_kg=2.5,
    )
    assert dec.next_action == "increase_load"
    assert dec.next_rep_target == 6


def test_wave_phase3_cycle_resets():
    dec = decide_wave(
        _sets(65, 6, n=3), week_in_block=3, increment_kg=2.5,
    )
    assert dec.next_action == "increase_load"
    assert dec.next_rep_target == 10
    assert dec.next_load_kg == 67.5


def test_wave_missed_reps_holds():
    dec = decide_wave(
        [SetSummary(load_kg=60, reps=8), SetSummary(load_kg=60, reps=7)],
        week_in_block=1, increment_kg=2.5,
    )
    assert dec.next_action == "hold"
    assert dec.next_rep_target == 10
