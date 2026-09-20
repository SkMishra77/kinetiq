"""Warm-up / cool-down generator.

Deterministic, uses only the target muscles and the working load of the first
compound. The generated sets are advisory: the planner surfaces them, Claude
formats them for the user.
"""
from __future__ import annotations


def general_warmup() -> list[dict]:
    return [
        {"kind": "cardio", "detail": "5 min easy bike / row / brisk walk"},
        {"kind": "mobility", "detail": "world's greatest stretch × 5/side"},
        {"kind": "mobility", "detail": "hip 90/90 → open book × 5/side"},
    ]


def muscle_specific(muscles: list[str]) -> list[dict]:
    drills = []
    if any(m in muscles for m in ("chest", "front_delts", "triceps")):
        drills.append({"kind": "activation", "detail": "band pull-apart × 15"})
        drills.append({"kind": "activation", "detail": "scap push-up × 8"})
    if any(m in muscles for m in ("lats", "upper_back", "rear_delts")):
        drills.append({"kind": "activation", "detail": "dead-hang × 20 s"})
        drills.append({"kind": "activation", "detail": "prone Y × 10"})
    if any(m in muscles for m in ("quads", "glutes", "hamstrings")):
        drills.append({"kind": "mobility", "detail": "bodyweight squat × 10"})
        drills.append({"kind": "activation", "detail": "glute bridge × 10"})
    if any(m in muscles for m in ("side_delts", "front_delts", "rear_delts")):
        drills.append({"kind": "mobility", "detail": "wall slides × 8"})
    return drills[:4]


def ramp_sets(working_load_kg: float | None) -> list[dict]:
    """Ramp-up sets before the first compound; ``None`` skips."""
    if working_load_kg is None or working_load_kg < 20:
        return []
    stages = [(0.40, 8), (0.60, 5), (0.80, 3)]
    return [
        {"load_kg": round(working_load_kg * pct, 1), "reps": reps, "kind": "ramp"}
        for pct, reps in stages
    ]


def cooldown(muscles: list[str]) -> list[dict]:
    stretches = [
        {"kind": "cardio", "detail": "3–5 min easy walk / bike"},
    ]
    if "chest" in muscles:
        stretches.append({"kind": "stretch", "detail": "doorway pec stretch × 30 s / side"})
    if "lats" in muscles or "upper_back" in muscles:
        stretches.append({"kind": "stretch", "detail": "child's pose × 30 s"})
    if "quads" in muscles:
        stretches.append({"kind": "stretch", "detail": "couch stretch × 30 s / side"})
    if "hamstrings" in muscles or "glutes" in muscles:
        stretches.append({"kind": "stretch", "detail": "seated forward fold × 30 s"})
    return stretches
