"""Analyzer end-to-end scenarios."""
from kinetiq.engine.analyzer import (
    ExerciseInput,
    SetInput,
    analyse_exercise,
    analyse_session,
)


def _bench(sets, **kw):
    return ExerciseInput(
        exercise_id=1, slug="bench", name="Bench",
        movement_pattern="horizontal_push", equipment="barbell",
        increment_kg=2.5, load_type="external", sets=sets,
        rep_min=6, rep_max=10, target_rir=2, **kw,
    )


def test_first_time_holds_at_baseline():
    ex = _bench([SetInput(load_kg=60, reps=8), SetInput(load_kg=60, reps=7),
                 SetInput(load_kg=57.5, reps=8)])
    v = analyse_exercise(ex)
    assert v.status == "first_time"
    assert v.next_action == "hold"
    assert v.top_load_kg == 60.0
    assert v.reps_at_top_load == 8
    assert v.best_e1rm_kg > 74.0


def test_progression_after_rep_max_hit():
    ex = _bench(
        [SetInput(load_kg=60, reps=10, rir=2)] * 3,
        prev_top_load_kg=60.0, prev_best_e1rm_kg=75.24, prev_tonnage_kg=60 * 23,
    )
    v = analyse_exercise(ex)
    assert v.status == "progressed"
    assert v.next_action == "increase_load"
    assert v.next_load_kg == 62.5


def test_pain_score_over_threshold_forces_swap():
    ex = _bench(
        [SetInput(load_kg=60, reps=8)] * 2,
        pain_score=6,
        prev_top_load_kg=60.0, prev_best_e1rm_kg=75.0, prev_tonnage_kg=800,
    )
    v = analyse_exercise(ex)
    assert v.next_action == "swap"
    assert v.pain_action == "stop"


def test_session_analysis_flags_regression_share():
    exs = [
        _bench([SetInput(load_kg=55, reps=6)] * 2,
               prev_top_load_kg=60.0, prev_best_e1rm_kg=75.0, prev_tonnage_kg=1400),
        _bench([SetInput(load_kg=60, reps=6)] * 2,
               prev_top_load_kg=60.0, prev_best_e1rm_kg=75.0, prev_tonnage_kg=800),
    ]
    exs[1].exercise_id = 2
    exs[1].slug = "row"
    out = analyse_session(exs)
    kinds = {f["kind"] for f in out.flags}
    # Both exercises regressed → recovery flag; both regressed → fatigue may or may not fire
    assert "recovery" in kinds or "fatigue" in kinds
