"""Parse workout-set shorthand into :class:`SetEntry` lists.

Grammar (informal):

* Entries separated by ``,`` ``;`` ``/`` ``and`` or newline.
* Each entry is a ``WEIGHT`` and one of the reps forms:

    - ``60kg x 8``            → 1 set, 60 kg × 8 reps
    - ``60 x 8, 60 x 7``      → 2 sets
    - ``60 x 8, 7, 8``        → weight carried forward, 3 sets
    - ``22.5 x 10 x 3``       → 3 sets of 10 reps @ 22.5 kg
    - ``3 x 10 @ 22.5``       → same
    - ``60x5 @ 8``            → RPE 8
    - ``60x5 rir 2``          → RIR 2
    - ``bw x 12``             → bodyweight
    - ``bw+10 x 8``           → bodyweight +10
    - ``60x5 (L/R)``          → alternating sides
    - ``60x5 F`` / ``60x5 fail`` → to-failure
    - ``(warmup) 40x8``       → warm-up
    - ``30s`` / ``60s`` (time-based); ``500m`` (distance)
"""
from __future__ import annotations
import re
from dataclasses import dataclass

from ..domain.models import SetEntry
from .weights import parse_weight, WeightParse

# ``x``, ``X``, ``×`` and ``*`` all mean "by".
_X = r"(?:x|X|×|\*)"

# Split on commas / semicolons / newlines / " and " (avoid splitting "and" in exercise text — this
# parser only receives the sets-shorthand string, so "and" is safe).
_ENTRY_SPLIT = re.compile(r"\s*(?:,|;|/(?=[^\s])|\n|\band\b)\s*")

# RPE / RIR suffixes: "@8", "@RPE8", "RPE 8", "RIR 2", "2RIR", "2 RIR"
# RPE only matches 1–10 (with optional .0/.5), so "@ 22.5" (a weight) is not mistaken for RPE.
_RPE_VAL = r"(?:10(?:\.0)?|[1-9](?:\.[05])?)"
_RPE_RE = re.compile(r"(?:@\s*|rpe\s*)(" + _RPE_VAL + r")\b", re.IGNORECASE)
_RIR_RE = re.compile(r"(?:^|\s|@)(?:rir\s*([0-6])|([0-6])\s*rir)\b", re.IGNORECASE)
_FAIL_RE = re.compile(r"\b(fail|failure|amrap|to[\s-]?failure)\b", re.IGNORECASE)
_WARMUP_RE = re.compile(r"\b(warm-?up|wu|w/u)\b|\((?:warm-?up|wu)\)", re.IGNORECASE)
_SIDE_RE = re.compile(r"\b(each|l/r|per\s*side|ea)\b", re.IGNORECASE)
# Duration accepts s / sec / seconds / min / minute(s). "m" alone is treated as meters below.
_DURATION_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(s|sec|secs|seconds?|min|mins|minutes?)\s*$", re.IGNORECASE
)
_DISTANCE_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(m|meters?|metres?|km|mi|miles?)\s*$", re.IGNORECASE
)


@dataclass
class ShorthandResult:
    sets: list[SetEntry]
    warnings: list[str]


def _strip_flags(entry: str) -> tuple[str, dict]:
    flags = {"rpe": None, "rir": None, "warmup": False, "to_failure": False,
             "unilateral": False}
    m = _RPE_RE.search(entry)
    if m:
        flags["rpe"] = float(m.group(1))
        entry = entry[:m.start()] + entry[m.end():]
    m = _RIR_RE.search(entry)
    if m:
        rir = m.group(1) or m.group(2)
        flags["rir"] = int(rir)
        entry = entry[:m.start()] + entry[m.end():]
    m = _FAIL_RE.search(entry)
    if m:
        flags["to_failure"] = True
        entry = entry[:m.start()] + entry[m.end():]
    if _WARMUP_RE.search(entry):
        flags["warmup"] = True
        entry = _WARMUP_RE.sub("", entry)
    if _SIDE_RE.search(entry):
        flags["unilateral"] = True
        entry = _SIDE_RE.sub("", entry)
    return entry.strip(), flags


def _apply_side(base: SetEntry, unilateral: bool) -> list[SetEntry]:
    if not unilateral:
        return [base]
    # For alternating/unilateral, produce a single row with side="both" but a note,
    # rather than duplicating — the engine treats bilateral sets homogenously.
    b = base.model_copy(update={"note": (base.note + "; each side") if base.note else "each side"})
    return [b]


def _mk_set(w: WeightParse, reps: int, flags: dict) -> SetEntry:
    return SetEntry(
        load_kg=w.kg,
        is_bodyweight=w.is_bodyweight,
        added_kg=w.added_kg if w.added_kg else None,
        assisted_kg=w.assisted_kg if w.assisted_kg else None,
        reps=reps,
        rpe=flags["rpe"],
        rir=flags["rir"],
        is_warmup=flags["warmup"],
        to_failure=flags["to_failure"],
        note=("unit=lb" if w.unit_source == "lb" else None),
    )


def _parse_reps_group(text: str) -> tuple[list[int], bool]:
    """Turn '8/7/6' or '10' or '10, 10, 8' into a rep list. Returns (reps, is_range)."""
    parts = re.split(r"[\s,/]+", text.strip())
    reps: list[int] = []
    for p in parts:
        if not p:
            continue
        if "-" in p:  # e.g. "8-10" range → use lower bound, flag range
            lo = int(re.split(r"-", p)[0])
            reps.append(lo)
        else:
            reps.append(int(p))
    return reps, False


def _try_duration(entry: str) -> SetEntry | None:
    m = _DURATION_RE.match(entry.strip())
    if m:
        val, unit = float(m.group(1)), m.group(2).lower()
        secs = int(val * 60) if unit.startswith("min") else int(val)
        return SetEntry(duration_s=secs)
    m = _DISTANCE_RE.match(entry.strip())
    if m:
        val, unit = float(m.group(1)), m.group(2).lower()
        meters = val * (1000 if unit.startswith("k") else 1609.344 if unit.startswith("mi") else 1.0)
        return SetEntry(distance_m=meters)
    return None


def parse_shorthand(text: str, default_weight: WeightParse | None = None) -> ShorthandResult:
    """Parse a shorthand string into a list of :class:`SetEntry`.

    Raises ValueError on unrecognisable fragments so the caller can surface a
    ``ToolError`` with the exact offending piece.
    """
    if not text or not text.strip():
        return ShorthandResult(sets=[], warnings=[])
    warnings: list[str] = []
    sets: list[SetEntry] = []
    last_weight: WeightParse | None = default_weight

    entries = [e.strip() for e in _ENTRY_SPLIT.split(text) if e.strip()]
    for raw in entries:
        entry, flags = _strip_flags(raw)

        # Duration/distance-only entries (cardio-style).
        dur = _try_duration(entry)
        if dur is not None:
            dur = dur.model_copy(update={
                "rpe": flags["rpe"], "rir": flags["rir"],
                "is_warmup": flags["warmup"], "to_failure": flags["to_failure"],
            })
            sets.append(dur)
            continue

        # Split around 'x' occurrences. We allow at most 3 tokens: W x R (x N).
        tokens = [t.strip() for t in re.split(_X, entry) if t.strip()]
        if len(tokens) == 1:
            # Bare "8" — reps only, use last_weight if any.
            reps_list, _ = _parse_reps_group(tokens[0])
            if not last_weight:
                raise ValueError(f"no weight established for {entry!r}")
            for r in reps_list:
                sets.append(_mk_set(last_weight, r, flags))
            continue

        # Detect "S x R @ W" or "S x R at W" forms: N x reps @ weight.
        at_split = re.split(r"\s+at\s+|\s*@\s*(?=\S)", entry, maxsplit=1)
        if len(at_split) == 2:
            left, right = at_split
            # Detect if left looks like "N x R" (starts with an integer + x + reps)
            left_tokens = [t.strip() for t in re.split(_X, left) if t.strip()]
            if len(left_tokens) == 2 and left_tokens[0].isdigit() and _looks_like_reps(left_tokens[1]):
                n_sets = int(left_tokens[0])
                reps_list, _ = _parse_reps_group(left_tokens[1])
                weight_txt = right.strip()
                w = parse_weight(weight_txt)
                last_weight = w
                reps = reps_list[0]
                for _ in range(n_sets):
                    sets.append(_mk_set(w, reps, flags))
                continue

        # Common forms: "W x R" or "W x R x N" or "W x R,R,R"
        # Try to parse first token as weight.
        try:
            w = parse_weight(tokens[0])
            last_weight = w
            if len(tokens) == 2:
                reps_list, _ = _parse_reps_group(tokens[1])
                for r in reps_list:
                    sets.append(_mk_set(w, r, flags))
            elif len(tokens) >= 3:
                reps = int(tokens[1])
                n = int(tokens[2])
                for _ in range(n):
                    sets.append(_mk_set(w, reps, flags))
            else:  # pragma: no cover
                raise ValueError(f"can't parse {entry!r}")
        except ValueError:
            # Fallback: perhaps "8 x 60" (reps first). Only accept when first token
            # is a small integer ≤ 30 and second parses as a weight.
            if tokens[0].isdigit() and int(tokens[0]) <= 30:
                try:
                    w = parse_weight(tokens[1])
                    reps = int(tokens[0])
                    last_weight = w
                    sets.append(_mk_set(w, reps, flags))
                    warnings.append(f"assumed reps×weight order for {entry!r}")
                    continue
                except ValueError:
                    pass
            raise ValueError(f"can't parse fragment {entry!r}")
    return ShorthandResult(sets=sets, warnings=warnings)


def _looks_like_reps(tok: str) -> bool:
    return bool(re.fullmatch(r"[0-9,/\s]+", tok)) and any(ch.isdigit() for ch in tok)
