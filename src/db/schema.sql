CREATE TABLE IF NOT EXISTS archives (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  tapestry_id TEXT,
  status TEXT NOT NULL DEFAULT 'created',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS etl_tasks (
  id TEXT PRIMARY KEY,
  archive_id TEXT NOT NULL REFERENCES archives(id),
  provider TEXT NOT NULL,
  interaction_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'created',
  extracted_count INTEGER NOT NULL DEFAULT 0,
  transformed_count INTEGER NOT NULL DEFAULT 0,
  uploaded_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  unique_key TEXT NOT NULL UNIQUE,
  tapestry_id TEXT,
  etl_task_id TEXT REFERENCES etl_tasks(id),
  provider TEXT NOT NULL,
  interaction_type TEXT NOT NULL,
  preview TEXT NOT NULL,
  payload TEXT NOT NULL,
  asset_uri TEXT,
  source TEXT,
  version TEXT NOT NULL,
  asat TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_threads_unique_key ON threads(unique_key);
CREATE INDEX IF NOT EXISTS idx_threads_etl_task_id ON threads(etl_task_id);
CREATE INDEX IF NOT EXISTS idx_threads_provider ON threads(provider);
CREATE INDEX IF NOT EXISTS idx_threads_asat ON threads(asat);
CREATE INDEX IF NOT EXISTS idx_etl_tasks_archive_id ON etl_tasks(archive_id);

