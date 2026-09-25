"""Golden cases for weekly_hard_sets and check_volume_bands."""
from __future__ import annotations

from kinetiq.engine.volume import check_volume_bands, weekly_hard_sets


class TestWeeklyHardSets:
    def test_primary_counted_full(self):
        entries = [{"primary": ["chest"], "secondary": ["triceps"], "working_sets": 4}]
        result = weekly_hard_sets(entries)
        assert result["chest"] == 4.0
        assert result["triceps"] == 2.0

    def test_multiple_entries_sum(self):
        entries = [
            {"primary": ["chest"], "secondary": [], "working_sets": 3},
            {"primary": ["chest"], "secondary": [], "working_sets": 4},
        ]
        assert weekly_hard_sets(entries)["chest"] == 7.0

    def test_empty(self):
        assert weekly_hard_sets([]) == {}


class TestCheckVolumeBands:
    def test_under_volume(self):
        flags = check_volume_bands({"chest": 5.0}, "muscle_gain")
        assert len(flags) == 1
        assert flags[0].status == "under"
        assert flags[0].band_low == 10
        assert flags[0].band_high == 20

    def test_over_volume(self):
        flags = check_volume_bands({"quads": 25.0}, "muscle_gain")
        assert len(flags) == 1
        assert flags[0].status == "over"
        assert flags[0].severity == "watch"

    def test_ok_volume_no_flags(self):
        flags = check_volume_bands({"chest": 12.0}, "muscle_gain")
        assert len(flags) == 0

    def test_boundary_low(self):
        flags = check_volume_bands({"chest": 10.0}, "muscle_gain")
        assert len(flags) == 0

    def test_boundary_high(self):
        flags = check_volume_bands({"chest": 20.0}, "muscle_gain")
        assert len(flags) == 0

    def test_strength_bands(self):
        flags = check_volume_bands({"chest": 5.0}, "strength")
        assert len(flags) == 1
        assert flags[0].status == "under"
        assert flags[0].band_low == 6

    def test_unknown_goal_uses_default(self):
        flags = check_volume_bands({"chest": 5.0}, "unknown_goal")
        assert len(flags) == 1
        assert flags[0].band_low == 8

    def test_multiple_muscles(self):
        flags = check_volume_bands(
            {"chest": 5.0, "lats": 15.0, "quads": 25.0}, "muscle_gain"
        )
        statuses = {f.muscle: f.status for f in flags}
        assert statuses["chest"] == "under"
        assert statuses["quads"] == "over"
        assert "lats" not in statuses


class TestAestheticVolumeBands:
    def test_vtaper_uses_per_muscle_bands(self):
        flags = check_volume_bands({"lats": 10.0}, "aesthetic_vtaper")
        assert len(flags) == 1
        assert flags[0].status == "under"
        assert flags[0].band_low == 16

    def test_vtaper_lats_ok_at_16(self):
        flags = check_volume_bands({"lats": 18.0}, "aesthetic_vtaper")
        assert len(flags) == 0

    def test_vtaper_obliques_over_at_10(self):
        flags = check_volume_bands({"obliques": 10.0}, "aesthetic_vtaper")
        assert len(flags) == 1
        assert flags[0].status == "over"
        assert flags[0].band_high == 8

    def test_vtaper_side_delts_high_priority(self):
        flags = check_volume_bands({"side_delts": 10.0}, "aesthetic_vtaper")
        assert len(flags) == 1
        assert flags[0].band_low == 16

    def test_classic_physique_chest_high_band(self):
        flags = check_volume_bands({"chest": 14.0}, "classic_physique")
        assert len(flags) == 1
        assert flags[0].status == "under"
        assert flags[0].band_low == 16

    def test_aesthetic_balanced_equal_bands(self):
        flags = check_volume_bands({"chest": 13.0, "lats": 13.0}, "aesthetic_balanced")
        assert len(flags) == 0

    def test_unknown_muscle_in_aesthetic_falls_back_to_flat(self):
        flags = check_volume_bands({"hip_flexors": 5.0}, "aesthetic_vtaper")
        assert len(flags) == 1
        assert flags[0].band_low == 8
