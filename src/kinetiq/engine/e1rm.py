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


from dataclasses import dataclass


@dataclass
class TestAttempt:
    kind: str            # 'warmup' | 'ramp' | 'attempt'
    load_kg: float
    reps: int
    rest_min: float
    notes: str


def plan_1rm_test(
    current_e1rm: float,
    increment_kg: float = 2.5,
) -> list[TestAttempt]:
    """Generate a 1RM testing protocol based on the user's current estimated max.

    Warm-up ramp: bar (or 40%), 50%, 70%, 80%.
    Working ramp: 90%.
    Attempts: 95% (opener), 100% (target), 102.5% (stretch).
    All loads rounded to the exercise's increment.
    """
    from .increments import round_load

    bar_weight = 20.0
    protocol: list[TestAttempt] = []

    protocol.append(TestAttempt(
        kind="warmup", load_kg=bar_weight, reps=10, rest_min=1.0,
        notes="empty bar / light; get moving",
    ))
    for pct, reps, rest, kind in [
        (0.50, 5, 1.5, "warmup"),
        (0.70, 3, 2.0, "ramp"),
        (0.80, 2, 3.0, "ramp"),
        (0.90, 1, 3.5, "ramp"),
    ]:
        load = round_load(current_e1rm * pct, increment_kg, "nearest")
        protocol.append(TestAttempt(
            kind=kind, load_kg=load, reps=reps,
            rest_min=rest,
            notes=f"{int(pct*100)}% of estimated 1RM",
        ))

    for pct, label, rest in [
        (0.95, "opener — conservative single", 4.0),
        (1.00, "target 1RM attempt", 5.0),
        (1.025, "stretch PR attempt (optional)", 5.0),
    ]:
        load = round_load(current_e1rm * pct, increment_kg, "nearest")
        protocol.append(TestAttempt(
            kind="attempt", load_kg=load, reps=1,
            rest_min=rest, notes=label,
        ))

    return protocol
