"""Tests for engine/recovery.py."""
from __future__ import annotations

from kinetiq.engine.recovery import estimate_recovery, muscle_readiness


class TestEstimateRecovery:
    def test_large_muscle_base_72h(self):
        est = estimate_recovery("quads", days_since=4)
        assert est.base_hours == 72
        assert est.status == "recovered"

    def test_small_muscle_base_48h(self):
        est = estimate_recovery("biceps", days_since=3)
        assert est.base_hours == 48
        assert est.status == "recovered"

    def test_fatigued_recently_trained(self):
        est = estimate_recovery("quads", days_since=1)
        assert est.status == "fatigued"
        assert est.recovery_pct < 60

    def test_partial_recovery(self):
        est = estimate_recovery("quads", days_since=2)
        assert est.status == "partial"
        assert 60 <= est.recovery_pct < 100

    def test_high_volume_adds_penalty(self):
        normal = estimate_recovery("chest", days_since=3, volume_last=4)
        heavy = estimate_recovery("chest", days_since=3, volume_last=8)
        assert heavy.effective_hours > normal.effective_hours
        assert heavy.recovery_pct < normal.recovery_pct

    def test_poor_sleep_adds_penalty(self):
        good = estimate_recovery("lats", days_since=3, sleep_avg=8.0)
        bad = estimate_recovery("lats", days_since=3, sleep_avg=5.0)
        assert bad.effective_hours > good.effective_hours

    def test_high_soreness_adds_penalty(self):
        ok = estimate_recovery("glutes", days_since=3, soreness=2)
        sore = estimate_recovery("glutes", days_since=3, soreness=5)
        assert sore.effective_hours > ok.effective_hours

    def test_zero_days_is_zero_pct(self):
        est = estimate_recovery("chest", days_since=0)
        assert est.recovery_pct == 0
        assert est.status == "fatigued"

    def test_unknown_muscle_uses_mid_base(self):
        est = estimate_recovery("hip_flexors", days_since=3)
        assert est.base_hours == 60


class TestMuscleReadiness:
    def test_returns_all_muscles(self):
        dsm = {"chest": 2, "biceps": 3}
        result = muscle_readiness(dsm)
        assert "chest" in result
        assert "biceps" in result
        assert result["biceps"]["status"] == "recovered"

    def test_volume_affects_readiness(self):
        dsm = {"quads": 2}
        vol = {"quads": 10.0}
        result = muscle_readiness(dsm, volume_by_muscle=vol)
        assert result["quads"]["status"] in ("fatigued", "partial")
