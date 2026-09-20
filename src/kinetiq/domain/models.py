"""Pydantic input/output models shared by tools."""
from __future__ import annotations
from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    Goal, Experience, Sex, GymType, EffortScale, MovementPattern,
    Equipment, LoadType, Laterality, Side, Feel, IssueKind, IssueStatus,
    SplitType, ProgressionModel, NextAction, AnalysisStatus, InsightKind, Severity,
)


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


# ---- Set / exercise entries (log_workout inputs) --------------------------

class SetEntry(_Base):
    """One recorded set. All fields optional so the parser can fill in later."""
    load_kg: Annotated[float | None, Field(default=None, ge=0, le=1000)]
    added_kg: Annotated[float | None, Field(default=None, ge=-500, le=500)]
    assisted_kg: Annotated[float | None, Field(default=None, ge=0, le=500)]
    reps: Annotated[int | None, Field(default=None, ge=0, le=500)]
    duration_s: Annotated[int | None, Field(default=None, ge=0, le=36_000)]
    distance_m: Annotated[float | None, Field(default=None, ge=0, le=200_000)]
    rpe: Annotated[float | None, Field(default=None, ge=1, le=10)]
    rir: Annotated[int | None, Field(default=None, ge=0, le=10)]
    side: Side = "both"
    is_warmup: bool = False
    to_failure: bool = False
    is_bodyweight: bool = False
    note: str | None = None


class ExerciseEntry(_Base):
    """One exercise in a workout report."""
    exercise: Annotated[str, Field(min_length=1, max_length=120,
                                    description="Free-form name or alias; the server resolves it")]
    sets: list[SetEntry] | None = None
    sets_shorthand: str | None = None
    status: Annotated[str, Field(default="done", pattern="^(done|skipped|substituted|partial)$")]
    substituted_for: str | None = None
    feel: Feel | None = None
    pain_score: Annotated[int | None, Field(default=None, ge=0, le=10)]
    pain_location: str | None = None
    form_notes: str | None = None
    notes: str | None = None


class WellnessInput(_Base):
    energy: Annotated[int | None, Field(default=None, ge=1, le=5)]
    fatigue: Annotated[int | None, Field(default=None, ge=1, le=5)]
    sleep_hours: Annotated[float | None, Field(default=None, ge=0, le=16)]
    sleep_quality: Annotated[int | None, Field(default=None, ge=1, le=5)]
    stress: Annotated[int | None, Field(default=None, ge=1, le=5)]
    soreness_level: Annotated[int | None, Field(default=None, ge=0, le=5)]
    session_rpe: Annotated[float | None, Field(default=None, ge=1, le=10)]
    bodyweight_kg: Annotated[float | None, Field(default=None, ge=30, le=300)]


# ---- Profile inputs -------------------------------------------------------

class EquipmentItem(_Base):
    equipment: Equipment
    available: bool = True
    min_kg: float | None = None
    max_kg: float | None = None
    increment_kg: float | None = None
    detail: str | None = None


class InjuryInput(_Base):
    body_region: str
    description: str
    status: Annotated[str, Field(pattern="^(past|active|recovering|resolved)$")] = "active"
    side: Side = "both"
    onset_on: str | None = None
    affected_patterns: list[MovementPattern] = []
    avoid_exercises: list[str] = []
    notes: str | None = None


class LimitationInput(_Base):
    description: str
    kind: Annotated[str, Field(pattern="^(mobility|medical|equipment|time|other)$")] = "other"
    affected_patterns: list[MovementPattern] = []


class BodyMeasurementsInput(_Base):
    neck: float | None = None
    shoulders: float | None = None
    chest: float | None = None
    waist: float | None = None
    hips: float | None = None
    left_arm: float | None = None
    right_arm: float | None = None
    left_forearm: float | None = None
    right_forearm: float | None = None
    left_thigh: float | None = None
    right_thigh: float | None = None
    left_calf: float | None = None
    right_calf: float | None = None


class ProfileUpdate(_Base):
    display_name: str | None = None
    date_of_birth: str | None = None
    age_years: Annotated[int | None, Field(default=None, ge=10, le=120)]
    sex: Sex | None = None
    height_cm: Annotated[float | None, Field(default=None, ge=100, le=250)]
    training_experience: Experience | None = None
    training_years: Annotated[float | None, Field(default=None, ge=0, le=80)]
    primary_goal: Goal | None = None
    secondary_goals: list[str] | None = None
    days_per_week: Annotated[int | None, Field(default=None, ge=1, le=7)]
    available_days: list[str] | None = None
    session_minutes: Annotated[int | None, Field(default=None, ge=15, le=240)]
    gym_type: GymType | None = None
    preferred_effort_scale: EffortScale | None = None
    timezone: str | None = None
    other_notes: str | None = None
    # Nested lists
    equipment: list[EquipmentItem] | None = None
    preferences_like: list[str] | None = None
    preferences_dislike: list[str] | None = None
    preferences_cannot: list[str] | None = None
    preferences_avoid: list[str] | None = None
    injuries: list[InjuryInput] | None = None
    limitations: list[LimitationInput] | None = None
    weight_kg: Annotated[float | None, Field(default=None, ge=30, le=300)]
    body_fat_pct: Annotated[float | None, Field(default=None, ge=2, le=70)]
    measurements: BodyMeasurementsInput | None = None
    change_reason: str | None = None


# ---- Program inputs -------------------------------------------------------

class TemplateExerciseInput(_Base):
    exercise: str
    sets: Annotated[int, Field(ge=1, le=12)] = 3
    rep_min: Annotated[int, Field(ge=1, le=200)] = 8
    rep_max: Annotated[int, Field(ge=1, le=200)] = 12
    target_rir: Annotated[int, Field(ge=0, le=6)] = 2
    rest_s: Annotated[int, Field(ge=15, le=600)] = 120
    tempo: str | None = None
    superset_group: str | None = None
    role: Annotated[str, Field(pattern="^(primary|secondary|isolation|core|conditioning|mobility)$")] = "primary"
    progression_rule: ProgressionModel | None = None
    increment_kg: float | None = None
    start_weight_kg: float | None = None
    is_optional: bool = False
    notes: str | None = None

    @field_validator("rep_max")
    @classmethod
    def _range(cls, v: int, info: Any) -> int:  # noqa: ANN401
        rmin = info.data.get("rep_min") or 0
        if v < rmin:
            raise ValueError("rep_max must be >= rep_min")
        return v


class SessionTemplateInput(_Base):
    key_name: str | None = None
    name: str
    focus: str | None = None
    target_muscles: list[str] = []
    est_minutes: int | None = None
    warmup: list[dict] | None = None
    cooldown: list[dict] | None = None
    exercises: list[TemplateExerciseInput]


class ProgramInput(_Base):
    name: str
    goal: Goal
    split_type: SplitType
    days_per_week: Annotated[int, Field(ge=1, le=7)]
    progression_model: ProgressionModel = "double_progression"
    block_length_weeks: Annotated[int, Field(ge=1, le=12)] = 4
    deload_policy: dict = {}
    rationale: str | None = None
    activate: bool = True
    sessions: list[SessionTemplateInput]


# ---- Analysis outputs (used by planner + logging tool) --------------------

class SetMetric(_Base):
    set_no: int
    load_kg: float | None = None
    reps: int | None = None
    effective_load_kg: float | None = None
    e1rm_kg: float | None = None
    e1rm_reliable: bool = True
    volume_kg: float | None = None
    rpe: float | None = None
    rir: int | None = None
    side: Side = "both"
    is_warmup: bool = False


class ExerciseVerdict(_Base):
    exercise: str
    exercise_id: int
    status: AnalysisStatus
    best_e1rm_kg: float | None = None
    delta_e1rm_pct: float | None = None
    top_load_kg: float | None = None
    reps_at_top_load: int | None = None
    tonnage_kg: float | None = None
    delta_tonnage_pct: float | None = None
    avg_rpe: float | None = None
    hit_all_reps: bool | None = None
    hit_rep_max_all_sets: bool | None = None
    prs: list[dict] = []
    next_action: NextAction = "hold"
    next_load_kg: float | None = None
    next_rep_target: int | None = None
    next_sets: int | None = None
    reason: str = ""


class SessionAnalysis(_Base):
    engine_version: str
    performance_score: float | None = None
    fatigue_score: float | None = None
    adherence_pct: float | None = None
    summary: str = ""
    flags: list[str] = []
    per_exercise: list[ExerciseVerdict] = []
