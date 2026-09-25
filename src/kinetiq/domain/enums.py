"""Enum-like literal groups shared across the codebase."""
from __future__ import annotations
from typing import Literal, Final

Goal = Literal[
    "muscle_gain", "fat_loss", "strength", "recomposition",
    "general_fitness", "endurance", "athletic",
    "aesthetic_vtaper", "aesthetic_balanced", "classic_physique",
]
Experience = Literal["beginner", "novice", "intermediate", "advanced"]
Sex = Literal["male", "female", "other", "unspecified"]
GymType = Literal["commercial", "home", "minimal", "bodyweight"]
EffortScale = Literal["rir", "rpe", "none"]

MovementPattern = Literal[
    "horizontal_push", "incline_push", "vertical_push",
    "horizontal_pull", "vertical_pull",
    "squat", "hinge", "lunge", "hip_thrust",
    "carry", "core_flexion", "core_anti_extension", "core_rotation",
    "calf", "arm_flexion", "arm_extension",
    "shoulder_isolation", "leg_isolation",
    "conditioning", "mobility", "other",
]
Equipment = Literal[
    "barbell", "dumbbell", "kettlebell", "cable", "machine", "smith",
    "bodyweight", "band", "trap_bar", "ez_bar", "plate", "other",
]
LoadType = Literal["external", "bodyweight", "bodyweight_plus", "assisted", "time", "distance"]
Laterality = Literal["bilateral", "unilateral", "alternating"]
Side = Literal["both", "left", "right"]
Feel = Literal["easy", "ok", "moderate", "hard", "very_hard"]
IssueKind = Literal["pain", "injury", "limitation"]
IssueStatus = Literal["open", "monitoring", "resolved"]
SplitType = Literal[
    "full_body", "upper_lower", "push_pull_legs",
    "ppl_upper_lower", "bro_split", "custom",
]
ProgressionModel = Literal[
    "double_progression", "linear", "rpe_autoregulated", "wave", "fixed",
]
NextAction = Literal[
    "increase_load", "add_reps", "hold", "reduce_load",
    "swap", "deload", "review_form", "calibrate",
]
AnalysisStatus = Literal[
    "first_time", "progressed", "maintained", "regressed",
    "plateau", "incomplete", "skipped",
]
InsightKind = Literal[
    "progress", "pr", "plateau", "fatigue", "recovery", "pain",
    "form", "adherence", "bodyweight", "program", "layoff", "volume", "frequency",
    "physique",
]
Severity = Literal["info", "watch", "action"]

# Canonical muscle taxonomy.
MUSCLES: Final[tuple[str, ...]] = (
    "chest", "front_delts", "side_delts", "rear_delts",
    "lats", "upper_back", "traps",
    "biceps", "triceps", "forearms",
    "quads", "hamstrings", "glutes", "adductors", "abductors",
    "calves",
    "abs", "obliques", "lower_back", "hip_flexors",
    "full_body", "cardiovascular",
)

# Default rest defaults by exercise role & goal (seconds).
DEFAULT_REST_S: Final[dict[str, int]] = {
    "primary_strength": 240,
    "primary_hypertrophy": 150,
    "secondary": 105,
    "isolation": 75,
    "core": 60,
    "conditioning": 60,
    "mobility": 45,
}
