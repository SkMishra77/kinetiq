"""Tests for engine/planner.py time estimation with supersets."""
from __future__ import annotations

from kinetiq.engine.planner import PlannedExercise, _estimate_minutes


def _pe(order, rest_s=90, sets=3, superset_group=None):
    return PlannedExercise(
        order=order, exercise=f"ex{order}", exercise_id=order, slug=f"ex-{order}",
        role="primary", sets=sets, rep_range=(8, 12), target_rir=2,
        rest_s=rest_s, tempo=None, suggested_load_kg=60.0, mode="hold",
        basis={}, notes=[], last_performance=None, substitutes=[],
        warmup_ramp=[], superset_group=superset_group,
    )


class TestEstimateMinutes:
    def test_solo_exercises(self):
        planned = [_pe(1, rest_s=90, sets=3), _pe(2, rest_s=90, sets=3)]
        mins = _estimate_minutes(planned)
        assert mins > 0

    def test_superset_saves_time(self):
        solo = [_pe(1, rest_s=120, sets=3), _pe(2, rest_s=120, sets=3)]
        paired = [
            _pe(1, rest_s=120, sets=3, superset_group="A"),
            _pe(2, rest_s=120, sets=3, superset_group="A"),
        ]
        solo_time = _estimate_minutes(solo)
        paired_time = _estimate_minutes(paired)
        assert paired_time < solo_time

    def test_mixed_solo_and_superset(self):
        planned = [
            _pe(1, rest_s=120, sets=3, superset_group="A"),
            _pe(2, rest_s=120, sets=3, superset_group="A"),
            _pe(3, rest_s=90, sets=3),
        ]
        mins = _estimate_minutes(planned)
        assert mins > 0

    def test_empty_list(self):
        assert _estimate_minutes([]) == 8
