"""Weight-string parsing: kg / lb / bw / bw+10 / assisted-20 ..."""
from __future__ import annotations
import re
from dataclasses import dataclass

LB_TO_KG = 0.45359237

# Matches: 60, 60kg, 60 kg, 132lb, 132 lbs, 22.5, +10, -20, "bw", "bw+10", "bw-20", "assisted 20", "bodyweight+5"
_NUM = r"(?P<val>-?\d+(?:[.,]\d+)?)"
_UNIT = r"(?P<unit>kg|kgs|lb|lbs|pounds?|kilos?)?"
_BW = re.compile(r"^\s*(?:bw|bodyweight)\s*(?P<sign>[+-])?\s*"
                 r"(?:" + _NUM + r"\s*" + _UNIT + r")?\s*$", re.IGNORECASE)
_ASSISTED = re.compile(r"^\s*assist(?:ed)?\s+" + _NUM + r"\s*" + _UNIT + r"\s*$", re.IGNORECASE)
_PLAIN = re.compile(r"^\s*" + _NUM + r"\s*" + _UNIT + r"\s*$", re.IGNORECASE)


@dataclass
class WeightParse:
    """Result of parsing a weight token."""
    kg: float | None                # external load, in kg (after lb→kg)
    is_bodyweight: bool = False
    added_kg: float = 0.0           # extra load added to bodyweight
    assisted_kg: float = 0.0        # assistance reducing effective load
    unit_source: str = "kg"         # "kg" or "lb"
    original: str = ""


def _to_kg(val: str, unit: str | None) -> tuple[float, str]:
    v = float(val.replace(",", "."))
    if unit and unit.lower().startswith(("lb", "pound")):
        return round(v * LB_TO_KG, 4), "lb"
    return v, "kg"


def parse_weight(text: str) -> WeightParse:
    """Turn a weight string into a :class:`WeightParse`.

    Examples::

        parse_weight("60kg")     → kg=60.0
        parse_weight("132lb")    → kg=59.87..., unit_source='lb'
        parse_weight("bw")       → is_bodyweight=True, kg=None
        parse_weight("bw+10")    → is_bodyweight, added_kg=10
        parse_weight("assisted 20") → assisted_kg=20
    """
    if text is None:
        raise ValueError("empty weight")
    s = str(text).strip()
    if not s:
        raise ValueError("empty weight")

    m = _ASSISTED.match(s)
    if m:
        kg, unit = _to_kg(m.group("val"), m.group("unit"))
        return WeightParse(kg=None, is_bodyweight=True, assisted_kg=abs(kg),
                           unit_source=unit, original=s)

    m = _BW.match(s)
    if m:
        val = m.group("val")
        if val is None:
            return WeightParse(kg=None, is_bodyweight=True, original=s)
        kg, unit = _to_kg(val, m.group("unit"))
        sign = m.group("sign") or ("+" if kg >= 0 else "-")
        if sign == "-":
            return WeightParse(kg=None, is_bodyweight=True, assisted_kg=abs(kg),
                               unit_source=unit, original=s)
        return WeightParse(kg=None, is_bodyweight=True, added_kg=abs(kg),
                           unit_source=unit, original=s)

    m = _PLAIN.match(s)
    if m:
        kg, unit = _to_kg(m.group("val"), m.group("unit"))
        return WeightParse(kg=kg, unit_source=unit, original=s)

    raise ValueError(f"unrecognised weight token: {text!r}")


def round_to_increment(kg: float, increment_kg: float) -> float:
    """Round ``kg`` to the nearest multiple of ``increment_kg``.

    A ``0`` or negative increment falls back to 0.5 kg to avoid divide-by-zero.
    """
    inc = increment_kg if increment_kg and increment_kg > 0 else 0.5
    return round(round(kg / inc) * inc, 4)
