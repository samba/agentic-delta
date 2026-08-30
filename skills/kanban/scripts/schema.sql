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

CREATE INDEX IF NOT EXISTS task_dependencies_dependency_idx ON task_dependencies(dependency);

CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS task_events_task_idx ON task_events(task_id);

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'question',
    state TEXT NOT NULL DEFAULT 'captured',
    closure TEXT,
    raw_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (kind IN ('idea', 'problem', 'concern', 'opportunity', 'question')),
    CHECK (state IN ('captured', 'researching', 'refining', 'planned', 'deferred', 'closed')),
    CHECK ((state = 'closed' AND closure IN ('realized', 'rejected')) OR
           (state <> 'closed' AND closure IS NULL))
);

CREATE INDEX IF NOT EXISTS intents_state_idx ON intents(state);

CREATE TABLE IF NOT EXISTS intent_work_links (
    intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (intent_id, task_id)
);

CREATE INDEX IF NOT EXISTS intent_work_links_task_idx ON intent_work_links(task_id);

CREATE TABLE IF NOT EXISTS research_references (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    publisher TEXT,
    reference_type TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    topics_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    relevance TEXT,
    constraints TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT,
    review_state TEXT NOT NULL DEFAULT 'needs_review',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (review_state IN ('needs_review', 'reviewed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS research_references_url_hash_idx
    ON research_references(url, COALESCE(content_hash, ''));

CREATE TABLE IF NOT EXISTS reference_intents (
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE CASCADE,
    intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    PRIMARY KEY (reference_id, intent_id)
);

CREATE TABLE IF NOT EXISTS reference_tasks (
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (reference_id, task_id)
);

CREATE INDEX IF NOT EXISTS reference_intents_intent_idx ON reference_intents(intent_id);
CREATE INDEX IF NOT EXISTS reference_tasks_task_idx ON reference_tasks(task_id);

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
