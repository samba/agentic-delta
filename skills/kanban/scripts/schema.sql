PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS constraints_kv (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progression_kv (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS columns (
    name TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    description TEXT,
    required_rules_json TEXT NOT NULL DEFAULT '[]',
    direction TEXT NOT NULL DEFAULT 'forward',
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS columns_position_idx ON columns(position);

CREATE TABLE IF NOT EXISTS column_transitions (
    from_column TEXT NOT NULL REFERENCES columns(name) ON DELETE CASCADE,
    to_column TEXT NOT NULL REFERENCES columns(name) ON DELETE CASCADE,
    rule TEXT,
    PRIMARY KEY (from_column, to_column)
);

CREATE TABLE IF NOT EXISTS column_wip_limits (
    column_name TEXT PRIMARY KEY REFERENCES columns(name) ON DELETE CASCADE,
    limit_value INTEGER NOT NULL CHECK (limit_value > 0)
);

CREATE TABLE IF NOT EXISTS backfill_goals (
    column_name TEXT PRIMARY KEY REFERENCES columns(name) ON DELETE CASCADE,
    target_value INTEGER NOT NULL CHECK (target_value >= 0),
    description TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    column_name TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'unassigned',
    scope TEXT,
    goal TEXT,
    blocker_json TEXT,
    priority TEXT,
    value_score REAL,
    effort_score REAL,
    wsjf TEXT,
    complexity TEXT,
    ambiguity TEXT,
    review_rigor TEXT,
    validation_status TEXT,
    readiness_json TEXT,
    plan_status TEXT,
    raw_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_column_idx ON tasks(column_name);
CREATE INDEX IF NOT EXISTS tasks_owner_idx ON tasks(owner);
CREATE INDEX IF NOT EXISTS tasks_validation_status_idx ON tasks(validation_status);

CREATE TABLE IF NOT EXISTS task_themes (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    theme TEXT NOT NULL,
    PRIMARY KEY (task_id, theme)
);

CREATE INDEX IF NOT EXISTS task_themes_theme_idx ON task_themes(theme);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dependency TEXT NOT NULL,
    PRIMARY KEY (task_id, dependency)
);

CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS task_events_task_idx ON task_events(task_id);

CREATE TABLE IF NOT EXISTS backlog_ideas (
    id TEXT PRIMARY KEY,
    summary TEXT,
    status TEXT,
    themes_json TEXT,
    raw_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clarifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    default_answer TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    answer TEXT,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
);

CREATE INDEX IF NOT EXISTS clarifications_status_idx ON clarifications(status);

CREATE TABLE IF NOT EXISTS principles (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS principles_theme_idx ON principles(theme);
