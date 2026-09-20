"""Golden tests for weight parsing."""
import pytest

from kinetiq.parsing.weights import parse_weight, round_to_increment


@pytest.mark.parametrize("txt,kg,bw,added,assisted,unit", [
    ("60kg", 60.0, False, 0.0, 0.0, "kg"),
    ("60 kg", 60.0, False, 0.0, 0.0, "kg"),
    ("60", 60.0, False, 0.0, 0.0, "kg"),
    ("22.5", 22.5, False, 0.0, 0.0, "kg"),
    ("bw", None, True, 0.0, 0.0, "kg"),
    ("bw+10", None, True, 10.0, 0.0, "kg"),
    ("bw-20", None, True, 0.0, 20.0, "kg"),
    ("assisted 20kg", None, True, 0.0, 20.0, "kg"),
])
def test_parse_weight(txt, kg, bw, added, assisted, unit):
    w = parse_weight(txt)
    assert w.kg == kg
    assert w.is_bodyweight is bw
    assert w.added_kg == added
    assert w.assisted_kg == assisted
    assert w.unit_source == unit


def test_lb_conversion_rounded():
    # 132 lb == 59.87 kg
    assert parse_weight("132lb").unit_source == "lb"
    assert 59.5 < parse_weight("132lb").kg < 60.0


def test_round_to_increment():
    assert round_to_increment(63.0, 2.5) == 62.5
    assert round_to_increment(63.0, 5.0) == 65.0
    assert round_to_increment(22.7, 2.0) == 22.0
