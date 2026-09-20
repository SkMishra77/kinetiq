-- Kinetiq initial schema.
-- Conventions:
--   * timestamps ISO-8601 UTC in TEXT columns ending in _at
--   * dates YYYY-MM-DD in TEXT columns ending in _on
--   * JSON stored in TEXT with CHECK(json_valid(col))
--   * booleans stored as INTEGER 0/1
--   * soft deletes: *_at nullable timestamp columns

CREATE TABLE settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT INTO settings(key, value, updated_at) VALUES
  ('engine_version', '1', datetime('now')),
  ('seed_version', '0', datetime('now')),
  ('timezone', 'Asia/Kolkata', datetime('now')),
  ('thresholds_json', '{}', datetime('now'));

-- ===== Profile ===========================================================
CREATE TABLE profile(
  id INTEGER PRIMARY KEY CHECK(id=1),
  display_name TEXT,
  date_of_birth TEXT,                                              -- YYYY-MM-DD
  age_years INTEGER,
  sex TEXT CHECK(sex IS NULL OR sex IN ('male','female','other','unspecified')),
  height_cm REAL CHECK(height_cm IS NULL OR (height_cm BETWEEN 100 AND 250)),
  training_experience TEXT CHECK(training_experience IN ('beginner','novice','intermediate','advanced')),
  training_years REAL,
  primary_goal TEXT CHECK(primary_goal IN ('muscle_gain','fat_loss','strength','recomposition','general_fitness','endurance','athletic')),
  secondary_goals TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(secondary_goals)),
  days_per_week INTEGER CHECK(days_per_week IS NULL OR (days_per_week BETWEEN 1 AND 7)),
  available_days TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(available_days)),
  session_minutes INTEGER CHECK(session_minutes IS NULL OR (session_minutes BETWEEN 15 AND 240)),
  gym_type TEXT CHECK(gym_type IS NULL OR gym_type IN ('commercial','home','minimal','bodyweight')),
  preferred_effort_scale TEXT NOT NULL DEFAULT 'rir' CHECK(preferred_effort_scale IN ('rir','rpe','none')),
  timezone TEXT,
  other_notes TEXT,
  onboarding_completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE profile_history(
  id INTEGER PRIMARY KEY,
  changed_at TEXT NOT NULL,
  changed_fields TEXT NOT NULL CHECK(json_valid(changed_fields)),
  snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
  reason TEXT
);

CREATE TABLE profile_equipment(
  id INTEGER PRIMARY KEY,
  equipment TEXT NOT NULL UNIQUE,
  available INTEGER NOT NULL DEFAULT 1,
  min_kg REAL,
  max_kg REAL,
  increment_kg REAL,
  detail TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE exercise_preferences(
  id INTEGER PRIMARY KEY,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('like','dislike','cannot','avoid')),
  reason TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(exercise_id)
);

CREATE TABLE injuries(
  id INTEGER PRIMARY KEY,
  body_region TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('past','active','recovering','resolved')),
  side TEXT NOT NULL DEFAULT 'na' CHECK(side IN ('left','right','both','na')),
  onset_on TEXT,
  resolved_on TEXT,
  affected_patterns TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(affected_patterns)),
  avoid_exercise_ids TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(avoid_exercise_ids)),
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE limitations(
  id INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('mobility','medical','equipment','time','other')),
  affected_patterns TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(affected_patterns)),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE body_metrics(
  id INTEGER PRIMARY KEY,
  measured_on TEXT NOT NULL,
  weight_kg REAL CHECK(weight_kg IS NULL OR (weight_kg BETWEEN 30 AND 300)),
  body_fat_pct REAL CHECK(body_fat_pct IS NULL OR (body_fat_pct BETWEEN 2 AND 70)),
  source TEXT NOT NULL CHECK(source IN ('onboarding','checkin','workout')),
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_body_metrics_on ON body_metrics(measured_on);

CREATE TABLE body_measurements(
  metric_id INTEGER NOT NULL REFERENCES body_metrics(id) ON DELETE CASCADE,
  site TEXT NOT NULL CHECK(site IN (
    'neck','shoulders','chest','waist','hips',
    'left_arm','right_arm','left_forearm','right_forearm',
    'left_thigh','right_thigh','left_calf','right_calf'
  )),
  value_cm REAL NOT NULL CHECK(value_cm BETWEEN 10 AND 200),
  PRIMARY KEY(metric_id, site)
);

CREATE TABLE checkins(
  id INTEGER PRIMARY KEY,
  checkin_on TEXT NOT NULL UNIQUE,
  bodyweight_kg REAL,
  sleep_hours REAL CHECK(sleep_hours IS NULL OR (sleep_hours BETWEEN 0 AND 16)),
  sleep_quality INTEGER CHECK(sleep_quality IS NULL OR (sleep_quality BETWEEN 1 AND 5)),
  energy INTEGER CHECK(energy IS NULL OR (energy BETWEEN 1 AND 5)),
  soreness_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(soreness_json)),
  stress INTEGER CHECK(stress IS NULL OR (stress BETWEEN 1 AND 5)),
  resting_hr INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- ===== Exercise library ==================================================
CREATE TABLE exercises(
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  movement_pattern TEXT NOT NULL CHECK(movement_pattern IN (
    'horizontal_push','incline_push','vertical_push',
    'horizontal_pull','vertical_pull',
    'squat','hinge','lunge','hip_thrust',
    'carry','core_flexion','core_anti_extension','core_rotation',
    'calf','arm_flexion','arm_extension',
    'shoulder_isolation','leg_isolation',
    'conditioning','mobility','other'
  )),
  equipment TEXT NOT NULL CHECK(equipment IN (
    'barbell','dumbbell','kettlebell','cable','machine','smith',
    'bodyweight','band','trap_bar','ez_bar','plate','other'
  )),
  load_type TEXT NOT NULL CHECK(load_type IN (
    'external','bodyweight','bodyweight_plus','assisted','time','distance'
  )),
  laterality TEXT NOT NULL DEFAULT 'bilateral' CHECK(laterality IN ('bilateral','unilateral','alternating')),
  bodyweight_load_factor REAL NOT NULL DEFAULT 1.0,
  primary_muscles TEXT NOT NULL CHECK(json_valid(primary_muscles)),
  secondary_muscles TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(secondary_muscles)),
  is_compound INTEGER NOT NULL DEFAULT 1,
  default_increment_kg REAL NOT NULL DEFAULT 2.5,
  min_load_kg REAL,
  default_rest_s INTEGER,
  default_tempo TEXT,
  cues TEXT,
  contraindication_tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(contraindication_tags)),
  evidence_summary TEXT,
  selection_scores TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(selection_scores)),
  source TEXT NOT NULL CHECK(source IN ('seed','user')),
  needs_review INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE exercise_aliases(
  alias_norm TEXT PRIMARY KEY,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'seed'
);
CREATE INDEX ix_alias_ex ON exercise_aliases(exercise_id);

CREATE TABLE exercise_substitutions(
  exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
  substitute_id INTEGER NOT NULL REFERENCES exercises(id),
  reason TEXT NOT NULL CHECK(reason IN (
    'equipment','shoulder_pain','elbow_pain','knee_pain','low_back_pain',
    'wrist_pain','hip_pain','ankle_pain','neck_pain','variation','easier','harder'
  )),
  rank INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(exercise_id, substitute_id, reason)
);

-- ===== Program ===========================================================
CREATE TABLE programs(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  split_type TEXT NOT NULL CHECK(split_type IN (
    'full_body','upper_lower','push_pull_legs','ppl_upper_lower','bro_split','custom'
  )),
  days_per_week INTEGER NOT NULL CHECK(days_per_week BETWEEN 1 AND 7),
  progression_model TEXT NOT NULL DEFAULT 'double_progression' CHECK(progression_model IN (
    'double_progression','linear','rpe_autoregulated','wave','fixed'
  )),
  block_length_weeks INTEGER NOT NULL DEFAULT 4,
  deload_policy TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(deload_policy)),
  next_template_index INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('draft','active','completed','archived')),
  started_on TEXT,
  ended_on TEXT,
  rationale TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived_at TEXT
);
CREATE UNIQUE INDEX ux_programs_active ON programs(status) WHERE status='active';

CREATE TABLE program_blocks(
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  block_no INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('intro','accumulation','intensification','deload','custom')),
  planned_weeks INTEGER NOT NULL,
  volume_multiplier REAL NOT NULL DEFAULT 1.0,
  load_multiplier REAL NOT NULL DEFAULT 1.0,
  rir_offset INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('planned','active','done')),
  started_on TEXT,
  ended_on TEXT,
  UNIQUE(program_id, block_no)
);

CREATE TABLE session_templates(
  id INTEGER PRIMARY KEY,
  program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
  order_no INTEGER NOT NULL,
  key_name TEXT,                                          -- e.g. "Upper A" (nullable)
  name TEXT NOT NULL,
  focus TEXT,
  target_muscles TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(target_muscles)),
  est_minutes INTEGER,
  warmup_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warmup_json)),
  cooldown_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(cooldown_json)),
  UNIQUE(program_id, order_no)
);

CREATE TABLE template_exercises(
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL REFERENCES session_templates(id) ON DELETE CASCADE,
  order_no INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  sets INTEGER NOT NULL CHECK(sets BETWEEN 1 AND 12),
  rep_min INTEGER NOT NULL,
  rep_max INTEGER NOT NULL CHECK(rep_max >= rep_min),
  target_rir INTEGER NOT NULL DEFAULT 2,
  rest_s INTEGER NOT NULL DEFAULT 120,
  tempo TEXT,
  superset_group TEXT,
  role TEXT NOT NULL DEFAULT 'primary' CHECK(role IN ('primary','secondary','isolation','core','conditioning','mobility')),
  progression_rule TEXT,
  increment_kg REAL,
  start_weight_kg REAL,
  is_optional INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  replaced_by_id INTEGER REFERENCES template_exercises(id),
  created_at TEXT NOT NULL,
  deactivated_at TEXT,
  UNIQUE(template_id, order_no, active)
);

CREATE TABLE planned_sessions(
  id INTEGER PRIMARY KEY,
  planned_on TEXT NOT NULL,
  program_id INTEGER REFERENCES programs(id),
  template_id INTEGER REFERENCES session_templates(id),
  plan_json TEXT NOT NULL CHECK(json_valid(plan_json)),
  readiness_json TEXT,
  created_at TEXT NOT NULL,
  consumed_by_workout_id INTEGER,
  UNIQUE(planned_on, template_id)
);

-- ===== Workout log =======================================================
CREATE TABLE workouts(
  id INTEGER PRIMARY KEY,
  performed_on TEXT NOT NULL,
  started_at TEXT,
  duration_min INTEGER,
  program_id INTEGER REFERENCES programs(id),
  template_id INTEGER REFERENCES session_templates(id),
  block_id INTEGER REFERENCES program_blocks(id),
  planned_session_id INTEGER REFERENCES planned_sessions(id),
  status TEXT NOT NULL CHECK(status IN ('completed','partial','voided')),
  session_rpe REAL CHECK(session_rpe IS NULL OR (session_rpe BETWEEN 1 AND 10)),
  energy INTEGER CHECK(energy IS NULL OR (energy BETWEEN 1 AND 5)),
  fatigue INTEGER CHECK(fatigue IS NULL OR (fatigue BETWEEN 1 AND 5)),
  sleep_hours REAL,
  sleep_quality INTEGER,
  stress INTEGER,
  soreness_level INTEGER,
  bodyweight_kg REAL,
  location TEXT,
  notes TEXT,
  raw_report TEXT,
  voided_at TEXT,
  void_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_workouts_on ON workouts(performed_on);

CREATE TABLE workout_exercises(
  id INTEGER PRIMARY KEY,
  workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
  order_no INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  template_exercise_id INTEGER REFERENCES template_exercises(id),
  was_planned INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  skip_reason TEXT,
  substituted_for_id INTEGER REFERENCES exercises(id),
  feel TEXT CHECK(feel IS NULL OR feel IN ('easy','ok','moderate','hard','very_hard')),
  pain_score INTEGER CHECK(pain_score IS NULL OR (pain_score BETWEEN 0 AND 10)),
  pain_location TEXT,
  form_notes TEXT,
  notes TEXT,
  planned_sets INTEGER,
  planned_rep_min INTEGER,
  planned_rep_max INTEGER,
  planned_load_kg REAL
);
CREATE INDEX ix_wex_ex ON workout_exercises(exercise_id, workout_id);

CREATE TABLE sets(
  id INTEGER PRIMARY KEY,
  workout_exercise_id INTEGER NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
  set_no INTEGER NOT NULL,
  load_kg REAL,
  added_kg REAL DEFAULT 0,
  assisted_kg REAL DEFAULT 0,
  reps INTEGER CHECK(reps IS NULL OR (reps BETWEEN 0 AND 500)),
  duration_s INTEGER,
  distance_m REAL,
  rpe REAL CHECK(rpe IS NULL OR (rpe BETWEEN 1 AND 10)),
  rir INTEGER CHECK(rir IS NULL OR (rir BETWEEN 0 AND 10)),
  side TEXT NOT NULL DEFAULT 'both' CHECK(side IN ('both','left','right')),
  is_warmup INTEGER NOT NULL DEFAULT 0,
  to_failure INTEGER NOT NULL DEFAULT 0,
  effective_load_kg REAL,
  e1rm_kg REAL,
  e1rm_reliable INTEGER NOT NULL DEFAULT 1,
  volume_kg REAL,
  notes TEXT,
  UNIQUE(workout_exercise_id, set_no, side)
);

-- ===== Issues (pain / injury / limitation runtime state) =================
CREATE TABLE issues(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('pain','injury','limitation')),
  body_region TEXT NOT NULL,
  side TEXT NOT NULL DEFAULT 'both' CHECK(side IN ('left','right','both','na')),
  severity INTEGER NOT NULL DEFAULT 0 CHECK(severity BETWEEN 0 AND 10),
  description TEXT,
  onset_on TEXT,
  status TEXT NOT NULL CHECK(status IN ('open','monitoring','resolved')),
  restrictions_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(restrictions_json)),
  source TEXT NOT NULL DEFAULT 'report' CHECK(source IN ('onboarding','workout','report')),
  linked_exercise_id INTEGER REFERENCES exercises(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE INDEX ix_issues_open ON issues(status);

-- ===== Derived / analysis ================================================
CREATE TABLE exercise_stats(
  exercise_id INTEGER PRIMARY KEY REFERENCES exercises(id) ON DELETE CASCADE,
  sessions_count INTEGER NOT NULL DEFAULT 0,
  first_performed_on TEXT,
  last_performed_on TEXT,
  last_workout_id INTEGER,
  best_e1rm_kg REAL,
  best_e1rm_on TEXT,
  best_load_kg REAL,
  best_reps_at_best_load INTEGER,
  best_session_volume_kg REAL,
  last_e1rm_kg REAL,
  last_top_load_kg REAL,
  last_top_reps INTEGER,
  last_avg_rpe REAL,
  sessions_since_best INTEGER NOT NULL DEFAULT 0,
  plateau_count INTEGER NOT NULL DEFAULT 0,
  trend TEXT CHECK(trend IS NULL OR trend IN ('up','flat','down','insufficient')),
  recent_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(recent_json)),
  updated_at TEXT NOT NULL
);

CREATE TABLE personal_records(
  id INTEGER PRIMARY KEY,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  kind TEXT NOT NULL CHECK(kind IN ('e1rm','load','reps_at_load','session_volume','rep_max')),
  value REAL NOT NULL,
  reps INTEGER,
  load_kg REAL,
  set_id INTEGER REFERENCES sets(id),
  workout_id INTEGER NOT NULL REFERENCES workouts(id),
  achieved_on TEXT NOT NULL,
  previous_value REAL,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_pr_ex ON personal_records(exercise_id, kind, achieved_on);

CREATE TABLE session_analyses(
  id INTEGER PRIMARY KEY,
  workout_id INTEGER NOT NULL UNIQUE REFERENCES workouts(id) ON DELETE CASCADE,
  engine_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  performance_score REAL,
  fatigue_score REAL,
  adherence_pct REAL,
  summary TEXT,
  flags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(flags)),
  details_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(details_json))
);

CREATE TABLE exercise_analyses(
  id INTEGER PRIMARY KEY,
  session_analysis_id INTEGER NOT NULL REFERENCES session_analyses(id) ON DELETE CASCADE,
  workout_exercise_id INTEGER REFERENCES workout_exercises(id),
  exercise_id INTEGER NOT NULL,
  comparison_wex_id INTEGER,
  comparable_rep_range INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL CHECK(status IN ('first_time','progressed','maintained','regressed','plateau','incomplete','skipped')),
  e1rm_kg REAL,
  e1rm_delta_pct REAL,
  tonnage_kg REAL,
  tonnage_delta_pct REAL,
  top_load_kg REAL,
  reps_at_top_load INTEGER,
  reps_at_same_load_delta INTEGER,
  avg_rpe REAL,
  rpe_delta REAL,
  sets_planned INTEGER,
  sets_completed INTEGER,
  hit_all_reps INTEGER,
  hit_rep_max_all_sets INTEGER,
  next_action TEXT NOT NULL CHECK(next_action IN (
    'increase_load','add_reps','hold','reduce_load','swap','deload','review_form','calibrate'
  )),
  next_load_kg REAL,
  next_rep_target INTEGER,
  next_sets INTEGER,
  reason TEXT NOT NULL
);
CREATE INDEX ix_exan_ex ON exercise_analyses(exercise_id);

CREATE TABLE insights(
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  workout_id INTEGER REFERENCES workouts(id),
  exercise_id INTEGER REFERENCES exercises(id),
  kind TEXT NOT NULL CHECK(kind IN (
    'progress','pr','plateau','fatigue','recovery','pain','form',
    'adherence','bodyweight','program','layoff','volume','frequency'
  )),
  severity TEXT NOT NULL CHECK(severity IN ('info','watch','action')),
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  suggested_action TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','resolved','dismissed','expired','applied')),
  expires_on TEXT,
  resolved_at TEXT,
  resolution TEXT,
  source TEXT NOT NULL DEFAULT 'engine' CHECK(source IN ('engine','trainer','user')),
  dedupe_key TEXT
);
CREATE INDEX ix_insights_open ON insights(status, kind);
CREATE UNIQUE INDEX ux_insights_dedupe_open ON insights(dedupe_key) WHERE status='open' AND dedupe_key IS NOT NULL;

CREATE TABLE next_session_adjustments(
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('engine','trainer','user')),
  template_id INTEGER REFERENCES session_templates(id),
  template_exercise_id INTEGER REFERENCES template_exercises(id),
  exercise_id INTEGER REFERENCES exercises(id),
  adjustment_type TEXT NOT NULL CHECK(adjustment_type IN (
    'load','load_pct','reps','sets','swap','remove','add','rest','tempo','rir','note','deload','skip'
  )),
  value_json TEXT NOT NULL CHECK(json_valid(value_json)),
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','applied','dismissed','expired')),
  applies_until TEXT,
  consumed_by_workout_id INTEGER REFERENCES workouts(id),
  source_insight_id INTEGER REFERENCES insights(id)
);
CREATE INDEX ix_adj_pending ON next_session_adjustments(status, template_id, exercise_id);

CREATE TABLE trainer_notes(
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('preference','context','goal','schedule','health','decision','other')),
  note TEXT NOT NULL,
  exercise_id INTEGER REFERENCES exercises(id),
  program_id INTEGER REFERENCES programs(id),
  pinned INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1
);

-- ===== Knowledge base ====================================================
CREATE TABLE research_papers(
  id INTEGER PRIMARY KEY,
  pmid TEXT UNIQUE,
  doi TEXT UNIQUE,
  s2_id TEXT UNIQUE,
  openalex_id TEXT UNIQUE,
  title TEXT NOT NULL,
  abstract TEXT,
  tldr TEXT,
  year INTEGER,
  journal TEXT,
  authors_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(authors_json)),
  citation_count INTEGER,
  open_access_url TEXT,
  study_type_guess TEXT CHECK(study_type_guess IS NULL OR study_type_guess IN (
    'meta_analysis','systematic_review','rct','cohort','cross_sectional','review','other'
  )),
  providers_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(providers_json)),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE knowledge_notes(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('principle','finding','exercise_evidence')),
  slug TEXT UNIQUE,
  topic TEXT,
  exercise_id INTEGER REFERENCES exercises(id) ON DELETE CASCADE,
  goal_tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(goal_tags)),
  muscle_tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(muscle_tags)),
  claim TEXT NOT NULL,
  detail TEXT,
  strength TEXT NOT NULL DEFAULT 'moderate' CHECK(strength IN ('strong','moderate','limited','mixed','expert_opinion')),
  applies_to_goals TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(applies_to_goals)),
  source TEXT NOT NULL CHECK(source IN ('seed','curated','user')),
  verified_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE knowledge_citations(
  id INTEGER PRIMARY KEY,
  note_id INTEGER REFERENCES knowledge_notes(id) ON DELETE CASCADE,
  paper_id INTEGER REFERENCES research_papers(id),
  pmid TEXT,
  doi TEXT,
  title TEXT,
  year INTEGER,
  journal TEXT,
  key_finding TEXT,
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK(verification_status IN ('unverified','verified','failed')),
  verified_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_kn_notes_topic ON knowledge_notes(topic);
CREATE INDEX ix_kn_citations_note ON knowledge_citations(note_id);

CREATE TABLE research_cache(
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL CHECK(provider IN ('pubmed','semantic_scholar','openalex')),
  query_hash TEXT NOT NULL UNIQUE,
  query_text TEXT NOT NULL,
  params_json TEXT NOT NULL,
  response_json TEXT NOT NULL,
  http_status INTEGER,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE api_usage(
  provider TEXT NOT NULL,
  usage_on TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(provider, usage_on)
);

CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  args_preview TEXT,
  ok INTEGER NOT NULL,
  error_class TEXT,
  duration_ms INTEGER
);
CREATE INDEX ix_audit_at ON audit_log(at);

-- ===== Views =============================================================
CREATE VIEW v_muscle_last_trained AS
  SELECT m.value AS muscle, MAX(s.performed_on) AS last_on, COUNT(DISTINCT s.id) AS sessions_28d
  FROM workouts s
    JOIN workout_exercises we ON we.workout_id=s.id AND we.skipped=0
    JOIN exercises e ON e.id=we.exercise_id, json_each(e.primary_muscles) m
  WHERE s.status IN ('completed','partial') AND s.performed_on >= date('now','-28 days')
  GROUP BY m.value;
