# Analysis rules (single source of truth)

All numeric thresholds mirror `src/kinetiq/engine/thresholds.py`. Change them
there; this doc restates the values and the rationale for humans.

## e1RM

- Epley: `w · (1 + r / 30)` (primary).
- Brzycki: `w · 36 / (37 - r)` (secondary).
- We store `mean(Epley, Brzycki)` and mark it `reliable=True` when `1 ≤ r ≤ 12`.
  For `r > 12` we return Epley only and mark it `reliable=False`; those sets
  never generate a PR or count toward plateau.
- If the user gave RIR (or RPE), we use `r_eff = r + RIR` and `RIR = 10 - RPE`.

## Classification (per exercise vs the most recent non-voided exposure within 90 days)

- **progressed** when any of:
  - `Δ e1RM ≥ +1.0 %`
  - same top load AND reps at top load `≥ +1`
  - `Δ tonnage ≥ +2.5 %` AND `Δ avg RPE ≤ +1`
- **regressed** when any of:
  - `Δ e1RM ≤ −3.0 %`
  - `Δ tonnage ≤ −5.0 %` at same-or-higher RPE
- **maintained** otherwise. **first_time** when no comparison exists.

## Plateau

- `plateau_count` increments on any exposure that is not `progressed`.
- Warn at 3, action at 4 or more, both requiring at least 14 days of span.
- Suggested response ranks by RPE and volume: high avg RPE → deload; low
  working-set count → add a set; otherwise swap variation.

## Fatigue score (0..1)

Weighted mean:

- 30 % share of exercises that regressed this session
- 20 % 3-session RPE drift (clamped: +2 RPE units → 1.0)
- 15 % low energy (1..5, 5 fresh)
- 15 % self-reported fatigue (1..5, 5 fried)
- 10 % sleep below 7.5 h (linearly)
- 10 % soreness (0..5)

Missing components are renormalised. `≥ 0.5` = watch, `≥ 0.7` = action → the
engine opens a `fatigue/action` insight that recommends a deload; the deload
is only applied when the user calls `set_program_phase(start_deload)`.

## Pain

- `pain_score ≥ 6` → `next_action=swap`, open an `action` insight, mention a
  clinician in the reason string. Never diagnose.
- `pain_score ∈ [3, 5]` → `reduce_load` 10 %, form review note, `watch`
  insight.
- Two consecutive exposures with pain in `[3, 5]` on the same exercise → swap
  to the top-ranked entry in `exercise_substitutions` for the region.

## Load rules — double progression (default)

Given top working set `L` and target rep range `[rmin, rmax]`:

- Every working set at `rmax` with sufficient RIR → `L + max(increment, L · pct)`,
  rounded to the exercise's increment. `pct` is 2.5 % for upper-body compound,
  5 % for lower-body compound (`squat / hinge / lunge / hip_thrust`); isolations
  use the raw increment.
- Every working set ≥ `rmin` but not all at `rmax` → hold load, aim `+1 rep`.
- Any set below `rmin`, or RPE ≥ 9.5 and not all at `rmin` → reduce load
  7.5 % (rounded down).

## Load rules — linear (novice strength)

- Hit target reps every set → `L + increment`.
- Two consecutive misses → `L − 10 %`.

## Suggested load pipeline (`plan_next_session`)

1. Pending `next_session_adjustments` for this exercise (`load`, `load_pct`,
   `swap`, `note`).
2. Last `exercise_analyses.next_load_kg`.
3. `exercise_stats.last_top_load_kg`.
4. Template `start_weight_kg`.
5. `mode:"calibrate"` — no history known.

Modifiers, in order:

- Block `load_multiplier` (deloads / intensification).
- Active-issue load cap (multiplier).
- Layoff: last session > 7 days → ×0.9; > 21 days → ×0.8 and calibrate.
- Day-of readiness: energy ≤ 2 or sleep < 6 h → ×0.95 and −1 set.

Then round to the exercise's `increment_kg` (profile override first, then
`template_exercises.increment_kg`, then `exercises.default_increment_kg`).

## Increment defaults

`barbell 2.5 · trap_bar / ez_bar / smith 2.5 · dumbbell 2.0 per hand ·
cable 2.5 · machine 5.0 · plate 2.5 · kettlebell 4.0 · bodyweight 2.5 added ·
band 0 (progression is band change, not weight).`

## Weekly volume bands (hard sets per muscle / 7 days)

`muscle_gain / recomposition / fat_loss: 10–20 · strength: 6–15 ·
general_fitness / athletic / endurance: 8–15/16.`

The engine surfaces an `info` insight when the rolling 7-day tally is outside
the band for the user's goal.
