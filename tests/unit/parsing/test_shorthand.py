"""Golden tests for the sets-shorthand parser (the user's example strings)."""
import pytest

from kinetiq.parsing.sets_shorthand import parse_shorthand


def _summary(sets):
    return [(s.load_kg, s.reps, s.rpe, s.rir, s.is_warmup, s.to_failure,
             s.duration_s, s.distance_m, s.is_bodyweight, s.added_kg or 0,
             s.assisted_kg or 0) for s in sets]


@pytest.mark.parametrize("text,expected", [
    ("60kg × 8, 60kg × 7, 57.5kg × 8",
     [(60.0, 8, None, None, False, False, None, None, False, 0, 0),
      (60.0, 7, None, None, False, False, None, None, False, 0, 0),
      (57.5, 8, None, None, False, False, None, None, False, 0, 0)]),
    ("22.5kg × 10 × 3",
     [(22.5, 10, None, None, False, False, None, None, False, 0, 0)] * 3),
    ("55kg × 10, 55kg × 9, 50kg × 10",
     [(55.0, 10, None, None, False, False, None, None, False, 0, 0),
      (55.0, 9, None, None, False, False, None, None, False, 0, 0),
      (50.0, 10, None, None, False, False, None, None, False, 0, 0)]),
    ("60 x 8, 8, 7",
     [(60.0, 8, None, None, False, False, None, None, False, 0, 0),
      (60.0, 8, None, None, False, False, None, None, False, 0, 0),
      (60.0, 7, None, None, False, False, None, None, False, 0, 0)]),
    ("3 x 10 @ 22.5",
     [(22.5, 10, None, None, False, False, None, None, False, 0, 0)] * 3),
    ("bw x 12 x 3",
     [(None, 12, None, None, False, False, None, None, True, 0, 0)] * 3),
    ("bw+10 x 8",
     [(None, 8, None, None, False, False, None, None, True, 10.0, 0)]),
    ("60x5 @8",
     [(60.0, 5, 8.0, None, False, False, None, None, False, 0, 0)]),
    ("60x5 rir 2",
     [(60.0, 5, None, 2, False, False, None, None, False, 0, 0)]),
    ("(warmup) 40x8",
     [(40.0, 8, None, None, True, False, None, None, False, 0, 0)]),
    ("60x5 fail",
     [(60.0, 5, None, None, False, True, None, None, False, 0, 0)]),
    ("60s", [(None, None, None, None, False, False, 60, None, False, 0, 0)]),
    ("5 min", [(None, None, None, None, False, False, 300, None, False, 0, 0)]),
    ("500m", [(None, None, None, None, False, False, None, 500.0, False, 0, 0)]),
])
def test_shorthand(text, expected):
    r = parse_shorthand(text)
    assert _summary(r.sets) == expected


def test_shorthand_malformed_raises():
    with pytest.raises(ValueError):
        parse_shorthand("this is nonsense")
