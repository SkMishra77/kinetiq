"""One-rep-max estimators."""
from __future__ import annotations


def epley(weight_kg: float, reps: float) -> float:
    """Epley: ``w * (1 + r / 30)`` (used for reps ≥ 2)."""
    if reps <= 0:
        return 0.0
    if reps <= 1:
        return float(weight_kg)
    return float(weight_kg) * (1.0 + reps / 30.0)


def brzycki(weight_kg: float, reps: float) -> float:
    """Brzycki: ``w * 36 / (37 - r)`` (defined for reps < 37)."""
    if reps <= 0:
        return 0.0
    if reps <= 1:
        return float(weight_kg)
    denom = 37.0 - reps
    if denom <= 0:
        return float(weight_kg)
    return float(weight_kg) * 36.0 / denom


def e1rm(weight_kg: float | None, reps: int | None, rir: int | None = None) -> tuple[float | None, bool]:
    """Best estimate of 1RM from a completed set.

    Uses ``mean(Epley, Brzycki)``. When RIR is given, adds it to the reps
    (RPE→RIR conversion is the caller's job). Reliable only for effective reps
    1–12; sets with more are still returned but ``reliable`` is ``False``.
    """
    if weight_kg is None or reps is None or reps <= 0:
        return None, False
    r_eff = reps + (rir or 0)
    if r_eff <= 1:
        return float(weight_kg), True
    if r_eff > 12:
        # Epley only for high reps; not reliable.
        return round(epley(weight_kg, r_eff), 3), False
    return round((epley(weight_kg, r_eff) + brzycki(weight_kg, r_eff)) / 2.0, 3), True


def rir_from_rpe(rpe: float | None) -> int | None:
    if rpe is None:
        return None
    val = max(0.0, min(6.0, 10.0 - rpe))
    return int(round(val))
