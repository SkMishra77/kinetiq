"""Epley/Brzycki known-value tests."""
import pytest

from kinetiq.engine.e1rm import brzycki, e1rm, epley, rir_from_rpe


def test_epley_60x8():
    assert epley(60, 8) == pytest.approx(76.0)


def test_brzycki_60x8():
    assert brzycki(60, 8) == pytest.approx(74.4828, abs=1e-3)


def test_e1rm_reliable_up_to_12():
    val, ok = e1rm(60, 8)
    assert ok
    assert val == pytest.approx((76.0 + 74.4828) / 2.0, abs=0.05)


def test_e1rm_high_reps_unreliable():
    val, ok = e1rm(60, 20)
    assert ok is False
    assert val is not None


def test_e1rm_single_rep_is_weight():
    val, ok = e1rm(100, 1)
    assert ok is True
    assert val == 100.0


def test_e1rm_none_when_no_load():
    val, ok = e1rm(None, 8)
    assert val is None
    assert ok is False


def test_rir_from_rpe():
    assert rir_from_rpe(8) == 2
    assert rir_from_rpe(10) == 0
    assert rir_from_rpe(None) is None
