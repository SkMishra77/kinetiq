"""Pain response rules — never diagnostic, only decision heuristics."""
from __future__ import annotations

from dataclasses import dataclass

from .thresholds import PAIN_MODIFY_SCORE, PAIN_STOP_SCORE


@dataclass
class PainRecommendation:
    action: str                      # 'stop' | 'swap' | 'reduce' | 'watch' | 'none'
    load_multiplier: float = 1.0
    reason: str = ""
    severity: str = "info"           # info | watch | action


def evaluate(pain_score: int | None, previous_pain: list[int] | None = None) -> PainRecommendation:
    if pain_score is None or pain_score <= 0:
        return PainRecommendation("none", reason="no pain reported")
    if pain_score >= PAIN_STOP_SCORE:
        return PainRecommendation(
            "stop",
            reason=f"pain {pain_score}/10 — stop the exercise and consider a qualified clinician",
            severity="action",
        )
    prev = previous_pain or []
    recurring = sum(1 for p in prev[-2:] if p and p >= PAIN_MODIFY_SCORE)
    if recurring >= 2:
        return PainRecommendation(
            "swap",
            reason=f"pain ≥{PAIN_MODIFY_SCORE} on 3 consecutive exposures; swap to a same-pattern alternative",
            severity="action",
        )
    if pain_score >= PAIN_MODIFY_SCORE:
        return PainRecommendation(
            "reduce",
            load_multiplier=0.9,
            reason=f"pain {pain_score}/10; reduce load 10 % and review form",
            severity="watch",
        )
    return PainRecommendation("watch", reason="low-level discomfort; monitor", severity="info")
