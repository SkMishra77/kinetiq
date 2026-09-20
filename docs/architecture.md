# Kinetiq — architecture and code map

This document is the human-readable index of the codebase. Read it once to
get the mental model, then use the tree map (§ 2) to jump to the file you
need. It covers **what each file contains**, **how the pieces fit together
end-to-end**, **the training logic** the engine implements, and **where
exercise data comes from** and how it moves from a YAML file into the
suggestions Claude gives you.

---

## 1. Ten-second mental model

Kinetiq is a remote MCP server. You add its URL as a **custom connector** in
claude.ai. Claude is the trainer's voice. The server is:

- a **memory** (SQLite: profile, program, every set ever logged),
- a **calculator** (deterministic Python: e1RM, progression, plateau,
  fatigue, pain, planner), and
- a **librarian** (curated exercise-science library + live PubMed / Semantic
  Scholar / OpenAlex lookups, cached locally).

FastMCP 4 has no server-side LLM sampling, so nothing in this repo calls an
LLM at runtime. Claude interprets what the tools return.

A conversation looks like:

```
you → claude.ai
       ↓ MCP over HTTPS
Caddy (TLS) → kinetiq container → SQLite (data/kinetiq.db)
       │                                      │
       │ /mcp/<48-char token>                 │ persistent volume
       │ (any other path → 404)               │
       ▼                                      ▼
   tools (get_briefing, plan_next_session, log_workout, ...)
```

Every conversation Claude joins starts by calling `get_briefing` (steered by
three things: the server `instructions` message, each tool's description
text, and your paste-ready `docs/claude-project-instructions.md`). That
single call returns profile + active program + rotation position + recent
sessions + PRs + insights + readiness, so Claude never re-asks for
information the DB already has.

---

## 2. Repo tree, annotated

```
Kinetiq/
  pyproject.toml           dependencies + build metadata (fastmcp>=4, pydantic, httpx, rapidfuzz, typer, uvicorn)
  uv.lock                  pinned dependency graph (single source of truth for reproducible installs)
  .python-version          "3.12"
  .env.example             every KINETIQ_* env var, commented
  .gitignore .dockerignore
  Dockerfile               multi-stage uv build → non-root, read-only rootfs, /data volume, Python HEALTHCHECK
  compose.yaml             kinetiq + caddy + duckdns services under the "caddy" profile; ngrok under "ngrok"
  deploy/Caddyfile         auto-TLS via Let's Encrypt; only /mcp/* and /health reach upstream; access logs OFF

  README.md                one-page quickstart + connect-to-claude.ai steps
  CLAUDE.md                instructions for future Claude Code work on this repo
  docs/                    (this doc, adding-tools, analysis-rules, operations, claude-project-instructions)

  .claude/agents/*.md      five dev subagents (see § 8 in CLAUDE.md)
  .claude/settings.json    read-only allowlist for common bash commands

  scripts/                 gen_token.py · backup.sh · pull-backups.sh · restore.sh

  src/kinetiq/             ── application code ──
    __init__.py            __version__
    __main__.py            enables `python -m kinetiq`
    cli.py                 typer CLI (serve, migrate, seed, backup, restore, gen-token, print-url, verify-citations)
    settings.py            pydantic-settings; reads KINETIQ_* env; validates the 48-char token
    logging_config.py      JSON logging + RedactingFilter (scrubs the URL token from any log line)
    services.py            Services dataclass (Database + Settings) passed to every tool
    server.py              create_server(settings): FastMCP factory, middleware wiring, health route
    app.py                 build_asgi_app(): the object uvicorn actually runs

    db/
      connection.py        Database: WAL, foreign_keys=ON, busy_timeout, one writer lock, write()/read() ctx managers
      migrations.py        discovers migrations/*.sql, applies pending ones in version order (idempotent)
      migrations/
        0001_init.sql      the full schema in one file: profile, exercises, programs, workouts, analyses, knowledge, audit
      backup.py            VACUUM INTO + gzip + integrity_check + retention (14 daily + pre-migration snapshots)
      repos/               THE ONLY PLACE WITH SQL (rule enforced in CLAUDE.md)
        profile.py         profile + equipment + preferences + injuries + limitations + body metrics
        exercises.py       library lookup, alias resolution, custom-exercise create, substitutes
        programs.py        program lifecycle (archive/create/blocks/templates/template_exercises), rotation pointer
        workouts.py        workout / workout_exercises / sets writes; previous_exposure lookup; days_since_muscle
        checkins.py        daily check-in upsert (one row/day); bodyweight trend; readiness
        issues.py          pain/injury/limitation runtime state with restrictions JSON
        analysis.py        persists analyzer output → session_analyses, exercise_analyses, PRs, insights, adjustments
        knowledge.py       knowledge_notes + citations + research_cache
        audit.py           append-only tool-call audit rows (never fails a request)

    domain/                pydantic IO models + shared enums + dates
      enums.py             Goal, Experience, Sex, MovementPattern, Equipment, Feel, InsightKind, Severity, muscle taxonomy
      dates.py             timezone-aware today() (uses profile timezone), parse_date("today"|"yesterday"|ISO)
      models.py            SetEntry, ExerciseEntry, WellnessInput, ProfileUpdate, ProgramInput, ExerciseVerdict...

    parsing/               STRING → STRUCT
      weights.py           "60kg" / "132lb" / "bw" / "bw+10" / "assisted 20" → WeightParse
      sets_shorthand.py    "60kg × 8, 60kg × 7, 57.5kg × 8" / "22.5kg × 10 × 3" / "@8" / "rir 2" → [SetEntry]
      aliases.py           normalise() (expands abbreviations) + resolve() (rapidfuzz ≥ 88 threshold + candidates)

    engine/                PURE PYTHON, NO DB, TESTABLE IN ISOLATION
      thresholds.py        every numeric constant (progression 1 % / regression 3 %, fatigue 0.5 / 0.7, plateau 3 / 4, etc.)
      e1rm.py              Epley, Brzycki, mean e1RM (reliable when reps ≤ 12), RIR ↔ RPE
      increments.py        equipment-aware round-to-increment (barbell 2.5, dumbbell 2.0 per hand, machine 5.0, ...)
      progression.py       decide_double_progression, decide_linear
      plateau.py           plateau counter → warn @ 3 / action @ 4
      fatigue.py           weighted 0–1 score from RPE drift, regression share, energy, sleep, soreness
      pain.py              pain rules (≥ 6 stop, 3–5 modify, recurring → swap)
      volume.py            weekly hard-set tally per muscle (primary 1.0, secondary 0.5)
      analyzer.py          the one-call session analyzer → SessionAnalysisOutput
      loads.py             suggested-load pipeline (pending adj → last analysis → last top → template → calibrate)
      warmup.py            5-min general + muscle-specific drills + ramp sets on first compound + cool-down stretches
      rotation.py          cyclic next_template_index helper
      planner.py           assembles a SessionPlan from template context + history + readiness

    knowledge/
      seed_loader.py       loads exercises.yaml/principles.yaml/substitutions.yaml (idempotent, hash-gated)
      sanitize.py          strips HTML/control chars, truncates untrusted research text to 1 500 chars
      research/
        client.py          PubMed → S2 → OpenAlex fallback, 30-day cache, sanitised untrusted-text envelope

    briefing/
      builder.py           get_briefing payload: profile + program + recent + PRs + insights + adjustments + readiness

    tools/                 THIN MCP ADAPTERS (validate → service/engine → shape a dict; no SQL, no math)
      briefing.py          get_briefing
      profile.py           save_profile · log_checkin · log_pain_or_injury
      exercises.py         search_exercises · add_exercise · compare_exercises
      program.py           create_program · get_program · edit_session_template · set_program_phase
      planning.py          plan_next_session
      logging_tool.py      log_workout · amend_workout · analyze_workout
      history.py           get_exercise_history · get_training_history · update_insight
      knowledge.py         search_knowledge · search_research · save_finding
      export.py            export_training_data

    middleware/
      audit.py             on_call_tool → writes audit_log rows (tool name, args preview, ok/error, duration)

    data/                  seed content (see § 5)
      exercises.yaml       41 exercises: aliases, muscles, equipment, pattern, evidence_summary, selection_scores
      principles.yaml      13 training-principle notes with PMID citations
      substitutions.yaml   pattern → alternative when a body region is off-limits
      warmup_library.yaml  muscle → mobility/activation drills

  tests/                   pytest, asyncio_mode=auto; 54 tests, no network in the default run
    conftest.py            settings / fresh_db / seeded_db / server / client fixtures
    unit/parsing/          test_weights.py, test_shorthand.py, test_aliases.py — golden tables
    unit/engine/           test_e1rm.py, test_progression.py, test_analyzer.py
    tools/                 test_tool_contracts.py — snapshot of names, annotations, description first lines
    integration/           test_day1_day4.py — end-to-end Day-1 → Day-5 progression scenario
    smoke/                 test_http.py — /health returns 200; /mcp/wrong returns 404
    test_migrations.py     idempotent migrations + seed hash gate
    test_backup.py         VACUUM INTO → gz → restore → integrity_check round-trip
    golden/                tool_contracts.json — regenerated by the snapshot test
```

---

## 3. Runtime flow of a single conversation

1. **claude.ai opens the connector** and sends an MCP `initialize`. FastMCP
   replies with the server `instructions` string, telling Claude to call
   `get_briefing` first.
2. **`get_briefing`** (`tools/briefing.py` → `briefing/builder.py`) queries
   the DB via a handful of repos (`profile.py`, `programs.py`, `workouts.py`,
   `analysis.py`, `checkins.py`, `issues.py`) and returns a compact payload:
   profile, active program, rotation position, recent-session summaries,
   `days_since_muscle`, PRs, open insights, pending adjustments, readiness,
   and a `state` of `needs_onboarding | needs_program | ready` with a
   `suggested_next_call` hint.
3. If **onboarding** is incomplete Claude interviews you in chat, then makes
   one `save_profile` call. The tool merges scalars into the singleton
   `profile` row, resolves any exercise names in preferences/injuries via
   `exercises.resolve_name`, replaces list-like nested collections
   (`equipment`, `injuries`, `limitations`), records a `profile_history`
   snapshot, and opens `issues` rows for each active injury.
4. Once profile is ready and no program exists, Claude designs one and calls
   **`create_program`**. Every exercise is resolved against the library;
   unresolved names return `status:"needs_resolution"` and the program is
   *not* written. On success `programs`, `program_blocks`, `session_templates`
   and `template_exercises` are populated in one transaction, and the
   previous active program (if any) is soft-archived.
5. **"What should I do today?"** → **`plan_next_session`**
   (`tools/planning.py` → `engine/planner.py` → `engine/loads.py`). The
   planner reads the current template from `programs.next_template_index`,
   pulls each exercise's history from `exercise_stats`, and runs the
   suggested-load pipeline (see § 4). Warm-up and cool-down come from
   `engine/warmup.py`. Ramp sets are added to the first compound. The plan
   is persisted to `planned_sessions` (idempotent per date+template) so
   `log_workout` can link back to it later.
6. **After training** you paste your sets. Claude calls **`log_workout`**
   once with a list of exercises. Each entry's `sets_shorthand` is parsed
   (`parsing/sets_shorthand.py`), unresolved names get returned in
   `resolution.unresolved` without any writes (or, with
   `allow_new_exercises=true`, create provisional exercises flagged
   `needs_review=1`). The tool then:
   1. Loads template context (`rep_min`, `rep_max`, `target_rir`,
      `progression_rule`, `increment_kg`) so the engine classifies
      correctly.
   2. Builds a list of `ExerciseInput` records (including previous
      exposure metrics fetched with `workouts.previous_exposure` +
      `summarize_exercise_at`, and the previous pain history).
   3. Runs `engine/analyzer.py:analyse_session` (pure).
   4. Writes `workouts` + `workout_exercises` + `sets` (with each set's
      `effective_load_kg`, `e1rm_kg`, `volume_kg`).
   5. Persists analysis output via `db/repos/analysis.py`:
      `session_analyses`, `exercise_analyses`, PRs, dedupe-keyed insights,
      and any non-hold `next_session_adjustments`.
   6. Advances the rotation pointer if the workout linked to a template.
7. Everything is now visible in the next `get_briefing`. Rotation advanced,
   insights present, PRs recorded, next-session adjustments queued.

---

## 4. Suggested-load pipeline (the heart of `plan_next_session`)

Priority (`engine/loads.py`):

1. **Pending adjustment** (`next_session_adjustments`): `load`,
   `load_pct`, `swap`, `note`.
2. **Latest exercise analysis** (`exercise_analyses.next_load_kg`).
3. **Last top load** (`exercise_stats.last_top_load_kg`).
4. **Template start load** (`template_exercises.start_weight_kg`).
5. **`mode:"calibrate"`** — no history; the plan tells you to ramp to a set
   of `rep_max` at RIR 2–3 and log it.

Then modifiers, in order:

- **Block modifier**: `program_blocks.load_multiplier`. Deload block →
  ×0.85–0.9; intensification → ×1.0 with `rir_offset -1`.
- **Active-issue load cap**: any open issue whose `restrictions.load_cap_pct`
  is `< 1.0` caps the load.
- **Layoff**: last exposure > 7 days → ×0.9; > 21 days → ×0.8 and switch
  mode to `calibrate`.
- **Day-of readiness**: energy ≤ 2 or sleep < 6 h → ×0.95 and sets − 1.

Finally the load rounds to the exercise's increment (profile override →
template override → `exercises.default_increment_kg`).

Progression rules (`engine/progression.py`) implement the double-progression
default; strength/novice can use linear. Full formulas live in
`docs/analysis-rules.md`, which is the single source of truth mirroring the
constants in `engine/thresholds.py`.

---

## 5. Where exercise data comes from

Kinetiq deliberately uses **three layers**, not one, so the trainer works
offline and grows evidence over time.

### 5.1 Curated seed (ships in the repo)

`src/kinetiq/data/exercises.yaml` — hand-authored, ~40 core exercises today.
Each entry has:

```yaml
- slug: barbell-bench-press
  name: Barbell Bench Press
  movement_pattern: horizontal_push
  equipment: barbell
  load_type: external
  laterality: bilateral
  bodyweight_load_factor: 1.0        # only used for bodyweight moves
  primary_muscles: [chest]
  secondary_muscles: [triceps, front_delts]
  is_compound: true
  default_increment_kg: 2.5
  default_rest_s: 180
  aliases: [bench, bench press, bb bench, flat bench]
  cues: "Squeeze scapulae, feet planted, mild arch."
  contraindication_tags: [shoulder_impingement, wrist_flexion_pain]
  evidence_summary: "..."
  selection_scores: {muscle_gain: 5, strength: 5, fat_loss: 3, general_fitness: 4}
```

The **seed loader** (`knowledge/seed_loader.py`) is idempotent and safe:

- It hashes the YAML files (SHA-256 of names + bytes) into `seed_version`
  in the `settings` table. If the hash matches, seeding is a no-op.
- Otherwise it upserts each `exercises` row by `slug`, but the `UPDATE`
  clause only fires **when `exercises.source='seed'`**, so any custom rows
  the user added via `add_exercise` are never overwritten.
- Every alias goes into `exercise_aliases` (normalised via
  `parsing/aliases.normalise`, which lowercases, strips punctuation, expands
  `db → dumbbell`, `bb → barbell`, `ohp → overhead press`, `rdl → romanian
  deadlift`, etc.).
- Substitutions from `substitutions.yaml` become rows in
  `exercise_substitutions(reason, rank)` used by the planner when an active
  issue blocks the primary lift.

Migrations run first at startup; the seed loader runs after. Both are
transactional and idempotent.

### 5.2 User-added exercises (grow the library at runtime)

Two entry points:

- **`add_exercise` tool** — the intentional path. Claude calls it when you
  say "add farmer's carries to the library". `source='user'` is set;
  aliases you supply plus the canonical name are indexed.
- **Provisional exercises from `log_workout`** — if you type an exercise name
  the alias resolver can't match (rapidfuzz `token_set_ratio ≥ 88`), one of
  two things happens:
  - Default: `log_workout` returns
    `status:"needs_resolution"` with candidate suggestions and does *not*
    write anything.
  - With `allow_new_exercises=true`: a stub `exercises` row is created
    (`movement_pattern='other'`, `equipment='other'`, `needs_review=1`)
    and the alias table gets your typed name. You can clean it up later with
    `add_exercise(merge_into=...)` or by editing `exercises.yaml` and
    re-seeding.

### 5.3 Evidence layer (why an exercise is "good for X")

Two sources feed the `search_knowledge` / `compare_exercises` tools:

1. `src/kinetiq/data/principles.yaml` — 13 seed principle notes with
   PMID citations (volume dose-response, rep-range breadth, rest intervals,
   frequency, exercise order, tempo, proximity to failure, warm-up, pain
   modification, deload, sleep, cardio integration). Each citation is stored
   with `verification_status='unverified'` at seed time and marked
   `verified` (or `failed`) after `uv run kinetiq verify-citations` fetches
   the actual title from PubMed's `esummary` API and fuzzy-matches at
   ratio ≥ 80.
2. `save_finding` — Claude persists a curated conclusion (with the PMIDs it
   actually retrieved via `search_research`). The server rejects citations
   without a PMID or DOI.

### 5.4 Live research (grow the evidence on demand)

`knowledge/research/client.py` exposes a unified `search(...)` that runs the
query against PubMed E-utilities, Semantic Scholar and OpenAlex, merges
results by DOI/PMID/title, and stores them in `research_cache` for 30 days.
If a provider fails, the client falls back to the next and finally to the
stale cache; the response reports which providers were fresh, cached, or
errored so Claude can honestly say so. Every abstract passes through
`knowledge/sanitize.py` (HTML strip, control chars removed, truncated to
1 500 chars) and is returned inside a `{papers, notice, untrusted: true}`
envelope. Fetched text never enters server instructions, tool descriptions,
or the briefing.

### 5.5 The data flow, in one picture

```
YAML seed ── seed_loader.py (hash-gated upsert) ──▶  exercises, exercise_aliases, exercise_substitutions,
                                                     knowledge_notes(source='seed'), knowledge_citations

user typing ── log_workout (parse aliases via rapidfuzz) ──▶  workout_exercises, sets
   │                                        │
   │                                        └─ (unknown name AND allow_new_exercises=true)
   │                                              ──▶ exercises(source='user', needs_review=1)
   │
   ▼
plan_next_session ◀── suggested-load pipeline ◀── exercise_stats, exercise_analyses, next_session_adjustments

Claude asks "why this exercise?"
   │
   ▼
search_knowledge (seed principles + saved findings)
   │  (coverage="thin")
   ▼
search_research (PubMed/S2/OpenAlex; 30-day cache; sanitised envelope)
   │
   ▼
save_finding → knowledge_notes(source='curated') + knowledge_citations(verified once verify-citations runs)
```

---

## 6. Analysis logic in one page

Given a workout you just logged, the analyzer (`engine/analyzer.py`):

1. For each set, computes `effective_load_kg` (external + added − assisted,
   or bodyweight × factor + added for bodyweight moves).
2. Computes per-set `e1RM` (mean of Epley and Brzycki when reps ≤ 12).
3. Aggregates per-exercise: top load and reps at top load, tonnage
   (Σ `effective_load × reps`), average RPE, whether every working set hit
   `rep_min` and `rep_max`.
4. Fetches the **most recent non-voided prior exposure** for the exercise
   within 90 days (preferring the same `template_exercise_id`) and computes
   `Δ e1RM %`, `Δ tonnage %`, `Δ avg RPE`, `Δ reps at same load`.
5. Classifies the exercise:
   - **progressed** if `Δ e1RM ≥ +1.0 %` OR (top load equal AND
     reps `≥ +1`) OR (`Δ tonnage ≥ +2.5 %` AND `Δ avg RPE ≤ +1`).
   - **regressed** if `Δ e1RM ≤ −3.0 %` OR `Δ tonnage ≤ −5.0 %` at same or
     higher RPE.
   - **maintained** otherwise. **first_time** if no comparison exists.
6. Chooses `next_action`:
   - Pain rules dominate (`pain_score ≥ 6` → `swap` and refer clinician;
     3–5 → `reduce_load` 10 %; two consecutive on the same exercise → swap).
   - Otherwise runs the template's `progression_rule`
     (default `double_progression`): hit `rep_max` on every set → +2.5 %
     upper / +5 % lower rounded to the equipment increment; hit `rep_min`
     but not `rep_max` → hold and `+1 rep` next time; below `rep_min` or
     RPE ≥ 9.5 → `reduce_load` 7.5 %.
7. Detects PRs (`e1rm`, `load`, `reps_at_load`, `session_volume`, `rep_max`).
8. Computes a session-level fatigue score (weighted mean of regression
   share, RPE drift over 3 sessions, energy, self-reported fatigue, sleep,
   soreness). ≥ 0.5 → `watch` insight, ≥ 0.7 → `action` insight
   recommending a deload.
9. Emits `next_session_adjustments` rows for every non-hold action, valid
   for 21 days.

All numeric thresholds live in `engine/thresholds.py` and are mirrored in
`docs/analysis-rules.md`. Bump `ENGINE_VERSION` when the semantics change so
older `session_analyses` are visibly out-of-date.

---

## 7. Storage layout (SQLite)

- **Profile & context**: `profile` (singleton, id=1) · `profile_history` ·
  `profile_equipment` · `exercise_preferences` · `injuries` ·
  `limitations` · `body_metrics` + `body_measurements` · `checkins`.
- **Library**: `exercises` · `exercise_aliases` · `exercise_substitutions`.
- **Program**: `programs` (partial unique index on `status='active'`) ·
  `program_blocks` · `session_templates` · `template_exercises`
  (soft-deactivated via `active=0`, keeps history) · `planned_sessions`.
- **Log**: `workouts` (soft `voided_at`) · `workout_exercises` · `sets`.
- **Issues**: `issues` with `restrictions_json` (avoid patterns / exercise
  ids / load cap).
- **Analysis** (all recomputable from the log): `exercise_stats` ·
  `personal_records` · `session_analyses` · `exercise_analyses` ·
  `insights` (with a partial unique index on `(dedupe_key)` where
  `status='open'`) · `next_session_adjustments` · `trainer_notes`.
- **Knowledge**: `knowledge_notes` · `knowledge_citations` ·
  `research_papers` · `research_cache` · `api_usage`.
- **Audit**: `audit_log` (append-only tool-call trace).
- **Views**: `v_muscle_last_trained` powers `days_since_muscle`.

Conventions: ISO-8601 UTC in `*_at`, `YYYY-MM-DD` in `*_on`, JSON columns
carry `CHECK(json_valid(col))`, booleans as `INTEGER 0/1`, and soft deletes
use nullable `*_at` timestamps rather than DELETE.

---

## 8. Security surface

- **No login**. The MCP endpoint URL contains a 48-char url-safe token
  loaded from `KINETIQ_MCP_PATH_TOKEN`. Every other path returns 404 at both
  Caddy and the app. The token never enters logs (Caddy access log is off,
  uvicorn's is off, and `logging_config.RedactingFilter` scrubs it from any
  log record just in case).
- **`amend_workout` is the only tool with `destructive_hint=True`**. Its
  destructive branches (`void_session`) require `confirm=true`.
- **Rate limiting** (10 rps / burst 30) via FastMCP middleware. Response
  size capped at 400 KB.
- **Prompt-injection hygiene**. Text fetched from research APIs passes
  through `knowledge/sanitize.py`, is truncated to 1 500 chars, and is
  wrapped in a typed `{papers, notice, untrusted: true}` envelope. It never
  enters server `instructions`, tool descriptions, or the briefing.
- **Container hardening**. Multi-stage build, non-root UID 10001, read-only
  rootfs + `tmpfs:/tmp`, `cap_drop: ALL`, `no-new-privileges`, only
  `/data` writable, no host port exposed for the app (Caddy fronts it).

---

## 9. Where to look next

- **Change the trainer's default load-selection**: `engine/loads.py`
  (pipeline order + modifiers).
- **Change classification / plateau / fatigue thresholds**:
  `engine/thresholds.py` (and update `docs/analysis-rules.md` in the same
  commit).
- **Add an exercise or an evidence-cited principle**:
  `src/kinetiq/data/exercises.yaml` and `principles.yaml`, then
  `uv run kinetiq seed` (or restart the container).
- **Add a new MCP tool**: follow the checklist in `docs/adding-tools.md` —
  domain model → repo → engine/service → thin `tools/*.py` register →
  test → update the `EXPECTED_TOOLS` snapshot.
- **Deploy or restore**: `docs/operations.md`.
