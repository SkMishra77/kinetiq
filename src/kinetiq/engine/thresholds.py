"""All numeric constants for the analysis and planning engines.

Every threshold here has a docstring; mirrors ``docs/analysis-rules.md``. Values
can be overridden per-installation via ``settings.thresholds_json`` (loaded at
startup); the constants below are the code-level defaults.
"""
from __future__ import annotations
from dataclasses import dataclass

ENGINE_VERSION = "1.0"

# ---- Classification ------------------------------------------------------
PROGRESSED_E1RM_PCT = 1.0        # ≥ +1 % e1RM
PROGRESSED_TONNAGE_PCT = 2.5     # OR ≥ +2.5 % tonnage w/o RPE rise
REGRESSED_E1RM_PCT = -3.0        # ≤ −3 %
REGRESSED_TONNAGE_PCT = -5.0     # ≤ −5 % at same-or-higher RPE

PLATEAU_WARN_COUNT = 3           # sessions without a progression best
PLATEAU_ACTION_COUNT = 4
PLATEAU_MIN_SPAN_DAYS = 14
COMPARISON_WINDOW_DAYS = 90      # ignore prior exposure older than 90 days

# ---- Fatigue -------------------------------------------------------------
FATIGUE_WATCH = 0.5              # session score
FATIGUE_ACTION = 0.7
LOW_SLEEP_HOURS = 6.0
LOW_ENERGY_THRESHOLD = 2         # (out of 5)
HIGH_FATIGUE_THRESHOLD = 4

# ---- Pain ----------------------------------------------------------------
PAIN_STOP_SCORE = 6              # ≥ this → stop + clinician insight
PAIN_MODIFY_SCORE = 3            # ≥ this → load -10 %, form review

# ---- Load rules ---------------------------------------------------------
LOAD_REDUCE_PCT_HYPERTROPHY = 0.925    # −7.5 %
LOAD_REDUCE_PCT_LINEAR = 0.90          # −10 %
LOAD_READINESS_REDUCE_PCT = 0.95       # low readiness (−5 %)
LAYOFF_LOAD_PCT_MEDIUM = 0.9           # 7–21 days off
LAYOFF_LOAD_PCT_LONG = 0.8             # > 21 days
LAYOFF_MEDIUM_DAYS = 7
LAYOFF_LONG_DAYS = 21

# ---- Equipment increment defaults (kg) ----------------------------------
DEFAULT_INCREMENTS = {
    "barbell": 2.5,
    "trap_bar": 2.5,
    "ez_bar": 2.5,
    "smith": 2.5,
    "dumbbell": 2.0,       # per hand
    "cable": 2.5,
    "machine": 5.0,
    "plate": 2.5,
    "kettlebell": 4.0,
    "band": 0.0,           # progression is band change, not weight
    "bodyweight": 2.5,     # added-load fallback
    "other": 2.5,
}

# ---- Weekly volume bands (hard sets per muscle per 7 days) --------------
WEEKLY_VOLUME_BANDS = {
    "muscle_gain": (10, 20),
    "recomposition": (10, 20),
    "strength": (6, 15),
    "fat_loss": (10, 20),
    "endurance": (8, 16),
    "general_fitness": (8, 15),
    "athletic": (8, 15),
}

# ---- Progression models --------------------------------------------------
COMPOUND_LOWER_PATTERNS = {"squat", "hinge", "lunge", "hip_thrust"}

INCREMENT_PCT_UPPER = 0.025      # 2.5 %
INCREMENT_PCT_LOWER = 0.05       # 5 %


@dataclass
class Thresholds:
    """Runtime-tunable snapshot loaded from ``settings.thresholds_json``."""

    progressed_e1rm_pct: float = PROGRESSED_E1RM_PCT
    progressed_tonnage_pct: float = PROGRESSED_TONNAGE_PCT
    regressed_e1rm_pct: float = REGRESSED_E1RM_PCT
    regressed_tonnage_pct: float = REGRESSED_TONNAGE_PCT
    plateau_warn: int = PLATEAU_WARN_COUNT
    plateau_action: int = PLATEAU_ACTION_COUNT
    plateau_min_span_days: int = PLATEAU_MIN_SPAN_DAYS
    fatigue_watch: float = FATIGUE_WATCH
    fatigue_action: float = FATIGUE_ACTION

    @classmethod
    def from_json(cls, data: dict) -> "Thresholds":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
