-- Cardio / conditioning sessions table
CREATE TABLE IF NOT EXISTS cardio_sessions(
  id INTEGER PRIMARY KEY,
  workout_id INTEGER REFERENCES workouts(id) ON DELETE SET NULL,
  performed_on TEXT NOT NULL,
  activity TEXT NOT NULL CHECK(activity IN (
    'run','bike','row','swim','walk','hiit','elliptical','stair_climb','jump_rope','other'
  )),
  duration_min INTEGER CHECK(duration_min IS NULL OR duration_min BETWEEN 1 AND 600),
  distance_km REAL CHECK(distance_km IS NULL OR distance_km >= 0),
  avg_hr INTEGER CHECK(avg_hr IS NULL OR avg_hr BETWEEN 30 AND 220),
  max_hr INTEGER CHECK(max_hr IS NULL OR max_hr BETWEEN 30 AND 250),
  zone TEXT CHECK(zone IS NULL OR zone IN ('zone1','zone2','zone3','zone4','zone5')),
  intensity TEXT CHECK(intensity IS NULL OR intensity IN ('easy','moderate','hard')),
  calories_est INTEGER CHECK(calories_est IS NULL OR calories_est >= 0),
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_cardio_on ON cardio_sessions(performed_on);
