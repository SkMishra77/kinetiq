"""Physique proportionality scoring and lagging-part detection.

Pure functions. No DB or I/O.

Ideal ratios draw on the "Grecian Ideal" / Steve Reeves proportions and the
golden ratio (1.618) for shoulder-to-waist. These are aspirational benchmarks,
not diagnostic standards.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- Ideal ratios per aesthetic goal -------------------------------------

IDEAL_RATIOS: dict[str, dict[str, float]] = {
    "aesthetic_vtaper": {
        "shoulder_to_waist": 1.618,
        "chest_to_waist": 1.35,
    },
    "aesthetic_balanced": {
        "shoulder_to_waist": 1.55,
        "chest_to_waist": 1.30,
        "arm_symmetry": 1.0,
        "leg_symmetry": 1.0,
        "calf_to_arm": 1.0,
    },
    "classic_physique": {
        "shoulder_to_waist": 1.618,
        "chest_to_waist": 1.40,
        "calf_to_arm": 1.0,
        "arm_symmetry": 1.0,
        "leg_symmetry": 1.0,
    },
}

# Maps measurement-site ratios to the muscles responsible for improvement.
RATIO_TO_MUSCLES: dict[str, dict[str, list[str]]] = {
    "shoulder_to_waist": {
        "increase": ["side_delts", "rear_delts", "lats"],
        "decrease": ["obliques"],
    },
    "chest_to_waist": {
        "increase": ["chest"],
        "decrease": ["obliques"],
    },
    "calf_to_arm": {
        "increase": ["calves"],
        "decrease": [],
    },
    "arm_symmetry": {
        "increase": ["biceps", "triceps"],
        "decrease": [],
    },
    "leg_symmetry": {
        "increase": ["quads", "hamstrings"],
        "decrease": [],
    },
}

SYMMETRY_TOLERANCE = 0.05  # 5% left-right difference is acceptable


@dataclass
class LaggingPart:
    muscles: list[str]
    ratio_name: str
    current: float
    target: float
    gap_pct: float
    suggestion: str


@dataclass
class ProportionReport:
    goal: str
    ratios: dict[str, float]
    targets: dict[str, float]
    score: int                             # 0-100
    lagging: list[LaggingPart] = field(default_factory=list)
    symmetry_issues: list[dict] = field(default_factory=list)


def _avg_pair(left: float | None, right: float | None) -> float | None:
    vals = [v for v in (left, right) if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _symmetry(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left == 0 or right == 0:
        return None
    return round(min(left, right) / max(left, right), 3)


def assess_proportions(
    measurements: dict[str, float | None],
    goal: str,
) -> ProportionReport:
    """Evaluate body proportions against the goal's ideal ratios.

    ``measurements`` is a flat ``{site: value_cm}`` dict matching the
    ``body_measurements`` sites: shoulders, waist, chest, hips, left_arm,
    right_arm, left_thigh, right_thigh, left_calf, right_calf, neck.
    """
    ideals = IDEAL_RATIOS.get(goal, IDEAL_RATIOS["aesthetic_balanced"])
    computed: dict[str, float] = {}
    lagging: list[LaggingPart] = []
    symmetry_issues: list[dict] = []

    shoulders = measurements.get("shoulders")
    waist = measurements.get("waist")
    chest = measurements.get("chest")
    left_arm = measurements.get("left_arm")
    right_arm = measurements.get("right_arm")
    left_thigh = measurements.get("left_thigh")
    right_thigh = measurements.get("right_thigh")
    left_calf = measurements.get("left_calf")
    right_calf = measurements.get("right_calf")

    avg_arm = _avg_pair(left_arm, right_arm)
    avg_calf = _avg_pair(left_calf, right_calf)

    if shoulders and waist and waist > 0:
        computed["shoulder_to_waist"] = round(shoulders / waist, 3)
    if chest and waist and waist > 0:
        computed["chest_to_waist"] = round(chest / waist, 3)
    if avg_calf and avg_arm and avg_arm > 0:
        computed["calf_to_arm"] = round(avg_calf / avg_arm, 3)

    arm_sym = _symmetry(left_arm, right_arm)
    if arm_sym is not None:
        computed["arm_symmetry"] = arm_sym
    leg_sym = _symmetry(left_thigh, right_thigh)
    if leg_sym is not None:
        computed["leg_symmetry"] = leg_sym

    # Score and detect lagging parts
    scores: list[float] = []
    for ratio_name, target in ideals.items():
        actual = computed.get(ratio_name)
        if actual is None:
            continue
        if ratio_name in ("arm_symmetry", "leg_symmetry"):
            pct = actual * 100
            scores.append(min(100.0, pct))
            if actual < (1.0 - SYMMETRY_TOLERANCE):
                gap = round((1.0 - actual) * 100, 1)
                mapping = RATIO_TO_MUSCLES.get(ratio_name, {})
                side = "left" if (
                    (ratio_name == "arm_symmetry" and left_arm and right_arm and left_arm < right_arm)
                    or (ratio_name == "leg_symmetry" and left_thigh and right_thigh and left_thigh < right_thigh)
                ) else "right"
                symmetry_issues.append({
                    "ratio": ratio_name, "value": actual, "weaker_side": side,
                    "gap_pct": gap,
                })
        else:
            ratio_score = min(100.0, (actual / target) * 100)
            scores.append(ratio_score)
            if actual < target:
                gap = round((target - actual) / target * 100, 1)
                mapping = RATIO_TO_MUSCLES.get(ratio_name, {})
                muscles = mapping.get("increase", [])
                suggestion = f"increase {', '.join(muscles)} volume (+2-4 sets/week)" if muscles else "see trainer"
                lagging.append(LaggingPart(
                    muscles=muscles,
                    ratio_name=ratio_name,
                    current=actual,
                    target=target,
                    gap_pct=gap,
                    suggestion=suggestion,
                ))

    overall_score = int(round(sum(scores) / max(1, len(scores)))) if scores else 0

    return ProportionReport(
        goal=goal,
        ratios=computed,
        targets=ideals,
        score=overall_score,
        lagging=lagging,
        symmetry_issues=symmetry_issues,
    )
