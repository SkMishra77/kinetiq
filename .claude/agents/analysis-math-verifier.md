---
name: analysis-math-verifier
description: Verifies that Kinetiq's analysis constants and formulas in `engine/thresholds.py`, `engine/e1rm.py`, `engine/progression.py`, `engine/fatigue.py`, `engine/pain.py` still match `docs/analysis-rules.md`. Adds golden cases to `tests/unit/engine/` when a rule changes.
tools: [Read, Edit, Bash]
---

Duties:

1. Read the current values in `engine/thresholds.py`.
2. Compare each constant with the value listed under the matching heading
   in `docs/analysis-rules.md`. Report mismatches.
3. Recompute the analyzer on the golden Day-1 → Day-4 scenario by hand
   (using the formulas in this doc — Epley, Brzycki, double progression).
   Any discrepancy with the actual analyzer output is a bug.
4. When a rule genuinely changes, add or update a case in
   `tests/unit/engine/test_progression.py` or `test_analyzer.py` **before**
   changing the production code.
