"""Tests for engine/frequency.py."""
from __future__ import annotations

from kinetiq.engine.frequency import check_frequency


class TestCheckFrequency:
    def test_within_threshold_no_flags(self):
        flags = check_frequency({"chest": 3, "lats": 5}, "muscle_gain", days_per_week=4)
        assert flags == []

    def test_over_threshold_flagged(self):
        flags = check_frequency({"chest": 8}, "muscle_gain", days_per_week=4)
        assert len(flags) == 1
        assert flags[0].muscle == "chest"
        assert flags[0].severity == "info"
        assert flags[0].threshold_days == 5

    def test_way_over_threshold_watch(self):
        flags = check_frequency({"chest": 14}, "muscle_gain", days_per_week=4)
        assert len(flags) == 1
        assert flags[0].severity == "watch"

    def test_lower_frequency_goal_uses_7_days(self):
        flags = check_frequency({"chest": 6}, "strength", days_per_week=3)
        assert flags == []

    def test_strength_over_7(self):
        flags = check_frequency({"chest": 9}, "strength", days_per_week=3)
        assert len(flags) == 1
        assert flags[0].threshold_days == 7

    def test_muscle_gain_low_days_per_week_uses_7(self):
        flags = check_frequency({"chest": 6}, "muscle_gain", days_per_week=3)
        assert flags == []

    def test_muscle_gain_high_days_per_week_uses_5(self):
        flags = check_frequency({"chest": 6}, "muscle_gain", days_per_week=5)
        assert len(flags) == 1
        assert flags[0].threshold_days == 5

    def test_multiple_muscles(self):
        flags = check_frequency(
            {"chest": 2, "lats": 10, "quads": 20},
            "muscle_gain", days_per_week=4,
        )
        muscles = {f.muscle for f in flags}
        assert "chest" not in muscles
        assert "lats" in muscles
        assert "quads" in muscles

    def test_unknown_goal_defaults_to_7(self):
        flags = check_frequency({"chest": 8}, "unknown")
        assert len(flags) == 1
        assert flags[0].threshold_days == 7
