"""Tests for engine/proportions.py."""
from __future__ import annotations

from kinetiq.engine.proportions import assess_proportions, ProportionReport


VTAPER_MEASUREMENTS = {
    "shoulders": 120.0,
    "waist": 78.0,
    "chest": 105.0,
    "left_arm": 35.0,
    "right_arm": 35.5,
    "left_thigh": 58.0,
    "right_thigh": 59.0,
    "left_calf": 37.0,
    "right_calf": 37.5,
}


class TestAssessProportions:
    def test_returns_report(self):
        report = assess_proportions(VTAPER_MEASUREMENTS, "aesthetic_vtaper")
        assert isinstance(report, ProportionReport)
        assert report.goal == "aesthetic_vtaper"
        assert 0 <= report.score <= 100

    def test_ratios_computed(self):
        report = assess_proportions(VTAPER_MEASUREMENTS, "aesthetic_vtaper")
        assert "shoulder_to_waist" in report.ratios
        assert "chest_to_waist" in report.ratios
        assert abs(report.ratios["shoulder_to_waist"] - 120.0 / 78.0) < 0.01

    def test_below_ideal_flags_lagging(self):
        narrow = {
            "shoulders": 90.0,
            "waist": 80.0,
            "chest": 95.0,
        }
        report = assess_proportions(narrow, "aesthetic_vtaper")
        assert len(report.lagging) > 0
        muscles_flagged = set()
        for lp in report.lagging:
            muscles_flagged.update(lp.muscles)
        assert "side_delts" in muscles_flagged or "lats" in muscles_flagged

    def test_at_ideal_no_lagging(self):
        ideal = {
            "shoulders": 130.0,
            "waist": 80.0,
            "chest": 110.0,
        }
        report = assess_proportions(ideal, "aesthetic_vtaper")
        assert len(report.lagging) == 0

    def test_symmetry_issues_detected(self):
        asym = {
            "left_arm": 30.0,
            "right_arm": 38.0,
        }
        report = assess_proportions(asym, "aesthetic_balanced")
        assert len(report.symmetry_issues) > 0
        assert report.symmetry_issues[0]["ratio"] == "arm_symmetry"

    def test_symmetry_ok_within_tolerance(self):
        sym = {
            "left_arm": 35.0,
            "right_arm": 35.5,
        }
        report = assess_proportions(sym, "aesthetic_balanced")
        arm_issues = [i for i in report.symmetry_issues if i["ratio"] == "arm_symmetry"]
        assert len(arm_issues) == 0

    def test_classic_physique_calf_to_arm(self):
        meas = {
            "left_arm": 40.0, "right_arm": 40.0,
            "left_calf": 38.0, "right_calf": 38.0,
            "shoulders": 120.0, "waist": 78.0, "chest": 108.0,
        }
        report = assess_proportions(meas, "classic_physique")
        assert "calf_to_arm" in report.ratios
        assert report.ratios["calf_to_arm"] < 1.0

    def test_empty_measurements(self):
        report = assess_proportions({}, "aesthetic_vtaper")
        assert report.score == 0
        assert report.lagging == []

    def test_unknown_goal_defaults_balanced(self):
        report = assess_proportions(VTAPER_MEASUREMENTS, "unknown_goal")
        assert report.goal == "unknown_goal"
        assert report.score > 0

    def test_score_perfect_at_or_above_ideal(self):
        perfect = {
            "shoulders": 135.0,
            "waist": 78.0,
            "chest": 115.0,
        }
        report = assess_proportions(perfect, "aesthetic_vtaper")
        assert report.score >= 95
