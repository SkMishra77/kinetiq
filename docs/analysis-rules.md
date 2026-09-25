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

## Load rules — RPE-autoregulated

RPE-based progression used when `progression_rule='rpe_autoregulated'`:

- All working sets at or below target RPE → increase load by increment
  (same % logic as double progression for upper/lower).
- Any set at RPE `>= target + 1` → hold load.
- Any set at RPE `>= 9.5` with reps below `rep_min` → reduce 7.5 %.
- If no RPE data is present on any set → fall back to double progression.

## Load rules — wave (undulating periodisation)

Used when `progression_rule='wave'`. Default 3-phase cycle per block:

- **Phase 1** (week 1): 3×10.
- **Phase 2** (week 2): 3×8 at higher load (+increment or +%).
- **Phase 3** (week 3): 3×6 at higher load.
- After phase 3 completes, cycle resets to phase 1 at `L + increment`.
- If target reps are not hit, the phase repeats at the same load.
- `week_in_block` determines the current phase (1-indexed, wraps).

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

`check_volume_bands()` in `engine/volume.py` compares the 7-day tally from
`weekly_hard_sets()` against the goal-specific band. Muscles below the low end
get an `under/info` flag; muscles above the high end get an `over/watch` flag.
These appear in the briefing payload under `volume_flags` and in `open_insights`
as `kind='volume'` entries.

## Auto-deload recommendation

The engine recommends a deload (emitting a `kind='deload'` flag/insight) when
any of these triggers fire:

1. **Sustained high fatigue**: fatigue score `>= 0.7` in at least 2 of the
   last 3 sessions.
2. **Widespread plateau**: `>= 3` exercises with `plateau_count >= 4`.
3. **Block length reached**: current block week `>=` planned `block_length_weeks`.

The deload is *not* auto-applied — it generates an insight that Claude surfaces;
the user or Claude must call `set_program_phase(action='start_deload')` to
actually enter the deload block.

## Aesthetic physique goals

Goals `aesthetic_vtaper`, `aesthetic_balanced`, and `classic_physique` activate
per-muscle volume bands from `AESTHETIC_VOLUME_PRIORITIES` in `thresholds.py`.

Key differences from flat bands:

- **V-taper**: lats 16–22, side delts 16–22, obliques 4–8 (minimise),
  traps 6–10 (low priority). Maximises shoulder-to-waist ratio.
- **Classic physique**: chest 16–22, lats 14–20, biceps/triceps 12–18,
  calves 10–16. Arms and calves are weighted equally ("calf-to-arm" ratio).
- **Aesthetic balanced**: all visible muscles 10–18 equally.

## Proportionality scoring (`engine/proportions.py`)

When the goal is aesthetic, `assess_proportions()` evaluates body measurements:

- **shoulder_to_waist**: target 1.618 (golden ratio) for V-taper/classic.
- **chest_to_waist**: target 1.35–1.40.
- **calf_to_arm**: target 1.0 for classic physique.
- **arm_symmetry / leg_symmetry**: flag if left-right ratio < 0.95.

Each ratio contributes to a 0–100 score. Ratios below target produce
`LaggingPart` entries with suggested muscles and volume adjustments.
The `get_physique_report` tool and the `physique_balance` briefing key
surface this data.
