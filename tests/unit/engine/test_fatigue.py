"""Tests for fatigue scoring and auto-deload recommendation."""
from __future__ import annotations

from kinetiq.engine.fatigue import (
    FatigueInputs,
    score,
    should_recommend_deload,
)


class TestFatigueScore:
    def test_fresh_is_zero(self):
        assert score(FatigueInputs()) == 0.0

    def test_all_regressed(self):
        s = score(FatigueInputs(regressed_share=1.0))
        assert s > 0.5

    def test_rpe_drift_contributes(self):
        s = score(FatigueInputs(rpe_drift=2.0))
        assert s > 0.3

    def test_low_energy(self):
        s = score(FatigueInputs(energy=1))
        assert s > 0.2


class TestShouldRecommendDeload:
    def test_no_deload_when_fresh(self):
        result = should_recommend_deload([0.2, 0.3, 0.1], {}, None, None)
        assert result is None

    def test_deload_on_sustained_high_fatigue(self):
        result = should_recommend_deload([0.8, 0.75, 0.6], {})
        assert result is not None
        assert result.should_deload is True
        assert "fatigue" in result.reason

    def test_deload_on_single_high_fatigue_not_enough(self):
        result = should_recommend_deload([0.8, 0.3, 0.2], {})
        assert result is None

    def test_deload_on_widespread_plateau(self):
        plateaus = {1: 5, 2: 4, 3: 6}
        result = should_recommend_deload([0.3], plateaus)
        assert result is not None
        assert "plateau" in result.reason

    def test_no_deload_with_few_plateaus(self):
        plateaus = {1: 5, 2: 4}
        result = should_recommend_deload([0.3], plateaus)
        assert result is None

    def test_deload_on_block_length_reached(self):
        result = should_recommend_deload([0.3], {}, block_week=4, block_length=4)
        assert result is not None
        assert "block week" in result.reason
        assert result.severity == "info"

    def test_no_deload_before_block_end(self):
        result = should_recommend_deload([0.3], {}, block_week=2, block_length=4)
        assert result is None

    def test_empty_scores_no_crash(self):
        result = should_recommend_deload([], {})
        assert result is None
