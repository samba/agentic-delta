PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_states (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    previous_state_id TEXT REFERENCES task_states(id) ON DELETE RESTRICT,
    next_state_id TEXT REFERENCES task_states(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL UNIQUE,
    wip_limit INTEGER CHECK (wip_limit IS NULL OR wip_limit > 0),
    required_fields_json TEXT NOT NULL DEFAULT '[]',
    assurance_on_entry INTEGER NOT NULL DEFAULT 0 CHECK (assurance_on_entry IN (0, 1)),
    worker_entry INTEGER NOT NULL DEFAULT 0 CHECK (worker_entry IN (0, 1)),
    review_queue INTEGER NOT NULL DEFAULT 0 CHECK (review_queue IN (0, 1)),
    requires_checks INTEGER NOT NULL DEFAULT 0 CHECK (requires_checks IN (0, 1)),
    requires_evidence INTEGER NOT NULL DEFAULT 0 CHECK (requires_evidence IN (0, 1)),
    requires_reviewed_references INTEGER NOT NULL DEFAULT 0 CHECK (requires_reviewed_references IN (0, 1)),
    terminal INTEGER NOT NULL DEFAULT 0 CHECK (terminal IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    intent_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'captured',
    closure TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (state IN ('captured', 'researching', 'refining', 'planned', 'deferred', 'closed')),
    CHECK ((state = 'closed' AND closure IN ('realized', 'rejected')) OR
           (state <> 'closed' AND closure IS NULL))
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    state_id TEXT NOT NULL REFERENCES task_states(id) ON DELETE RESTRICT,
    task_type TEXT NOT NULL DEFAULT 'work',
    summary TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'unassigned',
    scope TEXT,
    goal TEXT,
    priority_rank INTEGER,
    validation_status TEXT NOT NULL DEFAULT 'not_started',
    acceptance_json TEXT NOT NULL DEFAULT '[]',
    review_contract_json TEXT NOT NULL DEFAULT '{}',
    details_json TEXT NOT NULL DEFAULT '{}',
    parallelism TEXT NOT NULL DEFAULT 'serial' CHECK (parallelism IN ('serial', 'partitionable', 'fan-out')),
    min_workers INTEGER NOT NULL DEFAULT 1 CHECK (min_workers > 0),
    target_workers INTEGER NOT NULL DEFAULT 1 CHECK (target_workers >= min_workers),
    max_workers INTEGER NOT NULL DEFAULT 1 CHECK (max_workers >= target_workers),
    work_units_json TEXT NOT NULL DEFAULT '[]',
    reuse_policy TEXT NOT NULL DEFAULT 'serial-compatible',
    isolation TEXT NOT NULL DEFAULT 'task-bound',
    aggregation TEXT NOT NULL DEFAULT 'all-required',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_state_idx ON tasks(state_id);
CREATE INDEX IF NOT EXISTS tasks_type_idx ON tasks(task_type);
CREATE INDEX IF NOT EXISTS tasks_priority_idx ON tasks(priority_rank);

CREATE TABLE IF NOT EXISTS task_intents (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, intent_id)
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dependency_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, dependency_id),
    CHECK (task_id <> dependency_id)
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE (task_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS research_references (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    publisher TEXT,
    reference_type TEXT,
    published_at TEXT,
    retrieved_at INTEGER,
    topics_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    relevance TEXT,
    constraints TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT,
    review_state TEXT NOT NULL DEFAULT 'unreviewed',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

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

CREATE TABLE IF NOT EXISTS specialist_roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    description TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS task_checks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    check_type TEXT NOT NULL CHECK (check_type IN ('assurance', 'control')),
    criterion TEXT NOT NULL,
    specialist_role_id TEXT REFERENCES specialist_roles(id) ON DELETE RESTRICT,
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'passed', 'failed', 'not_applicable')),
    reviewer TEXT,
    reviewer_role_id TEXT REFERENCES specialist_roles(id) ON DELETE RESTRICT,
    reviewer_worker_id TEXT,
    finding TEXT,
    rationale TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (task_id, check_type, criterion, specialist_role_id)
);

CREATE INDEX IF NOT EXISTS task_checks_task_idx ON task_checks(task_id);
CREATE INDEX IF NOT EXISTS task_checks_role_idx ON task_checks(specialist_role_id);
CREATE INDEX IF NOT EXISTS task_checks_reviewer_role_idx ON task_checks(reviewer_role_id);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    check_id TEXT REFERENCES task_checks(id) ON DELETE SET NULL,
    artifact TEXT NOT NULL,
    revision TEXT,
    probe TEXT,
    result TEXT NOT NULL,
    producer TEXT NOT NULL,
    location TEXT,
    content_hash TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS guidance (
    id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    guidance_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    intended_outcome TEXT,
    rationale TEXT,
    verification_method TEXT,
    authority TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'retired')),
    effective_at INTEGER NOT NULL,
    superseded_at INTEGER,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS guidance_references (
    guidance_id TEXT NOT NULL,
    guidance_version INTEGER NOT NULL,
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL DEFAULT 'supports',
    PRIMARY KEY (guidance_id, guidance_version, reference_id),
    FOREIGN KEY (guidance_id, guidance_version)
        REFERENCES guidance(id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pull_capacity_leases (
    id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    lane TEXT NOT NULL,
    slots INTEGER NOT NULL CHECK (slots > 0),
    eligibility_json TEXT NOT NULL DEFAULT '{}',
    required_output TEXT NOT NULL,
    owner TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released', 'expired')),
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    renewed_at INTEGER,
    released_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (expires_at >= issued_at)
);

CREATE INDEX IF NOT EXISTS pull_leases_stage_idx ON pull_capacity_leases(stage, status);

-- A reservation binds a short-lived capacity lease to the task that the
-- downstream lane actually pulled.  It is not a worker run or heartbeat.
CREATE TABLE IF NOT EXISTS pull_capacity_reservations (
    id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL REFERENCES pull_capacity_leases(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    slots INTEGER NOT NULL CHECK (slots > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released')),
    reserved_at INTEGER NOT NULL,
    released_at INTEGER,
    UNIQUE (lease_id, task_id)
);

CREATE INDEX IF NOT EXISTS pull_reservations_lease_idx
    ON pull_capacity_reservations(lease_id, status);
CREATE INDEX IF NOT EXISTS pull_reservations_task_idx
    ON pull_capacity_reservations(task_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS pull_active_task_idx
    ON pull_capacity_reservations(task_id)
    WHERE status = 'active';

CREATE TRIGGER IF NOT EXISTS task_state_sequence_guard
BEFORE UPDATE OF state_id ON tasks
WHEN NEW.state_id <> OLD.state_id
 AND NOT EXISTS (
    SELECT 1 FROM task_states s
    WHERE s.id = OLD.state_id
      AND (s.previous_state_id = NEW.state_id OR s.next_state_id = NEW.state_id)
 )
BEGIN
    SELECT RAISE(ABORT, 'task state transition is not adjacent in the declared sequence');
END;

CREATE TRIGGER IF NOT EXISTS task_assurance_roster_guard
BEFORE UPDATE OF state_id ON tasks
WHEN NEW.state_id IN (SELECT id FROM task_states WHERE assurance_on_entry = 1)
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM specialist_roles r
        WHERE r.active = 1
          AND NOT EXISTS (
              SELECT 1 FROM task_checks c
              WHERE c.task_id = NEW.id
                AND c.check_type = 'assurance'
                AND c.specialist_role_id = r.id
                AND c.required = 1
          )
    ) THEN RAISE(ABORT, 'all active specialists must be enlisted in assurance checks') END;
END;

CREATE TRIGGER IF NOT EXISTS task_done_checks_guard
BEFORE UPDATE OF state_id ON tasks
WHEN NEW.state_id IN (SELECT id FROM task_states WHERE requires_checks = 1)
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM task_checks c
        WHERE c.task_id = NEW.id AND c.required = 1
          AND (c.status = 'pending' OR c.status = 'failed'
               OR (c.status = 'not_applicable' AND (c.rationale IS NULL OR trim(c.rationale) = '')))
    ) THEN RAISE(ABORT, 'all required task checks must pass or be justified as not-applicable') END;
END;

CREATE TRIGGER IF NOT EXISTS task_done_evidence_guard
BEFORE UPDATE OF state_id ON tasks
WHEN NEW.state_id IN (SELECT id FROM task_states WHERE requires_evidence = 1)
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM task_checks c
        WHERE c.task_id = NEW.id AND c.required = 1 AND c.status = 'passed'
          AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.check_id = c.id)
    ) THEN RAISE(ABORT, 'passed task checks require evidence before Done') END;
END;

CREATE TRIGGER IF NOT EXISTS task_reviewed_references_guard
BEFORE UPDATE OF state_id ON tasks
WHEN NEW.state_id IN (SELECT id FROM task_states WHERE requires_reviewed_references = 1)
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM reference_tasks rt
        JOIN research_references r ON r.id=rt.reference_id
        WHERE rt.task_id=NEW.id AND r.review_state='reviewed'
    ) THEN RAISE(ABORT, 'state requires at least one reviewed research reference') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM reference_tasks rt
        JOIN research_references r ON r.id=rt.reference_id
        WHERE rt.task_id=NEW.id AND r.review_state <> 'reviewed'
    ) THEN RAISE(ABORT, 'all linked research references must be reviewed') END;
END;

CREATE TRIGGER IF NOT EXISTS evidence_task_check_guard
BEFORE INSERT ON evidence
WHEN NEW.check_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM task_checks c WHERE c.id = NEW.check_id AND c.task_id = NEW.task_id
)
BEGIN
    SELECT RAISE(ABORT, 'evidence check does not belong to task');
END;

CREATE TRIGGER IF NOT EXISTS task_check_delete_guard
BEFORE DELETE ON task_checks
WHEN OLD.required = 1 AND EXISTS (
    SELECT 1 FROM task_states s JOIN tasks t ON t.state_id = s.id
    WHERE t.id = OLD.task_id
      AND (s.assurance_on_entry = 1 OR s.worker_entry = 1 OR s.review_queue = 1 OR s.requires_checks = 1)
)
BEGIN
    SELECT RAISE(ABORT, 'required task checks cannot be deleted while work is active');
END;

CREATE TRIGGER IF NOT EXISTS task_check_self_review_guard
BEFORE UPDATE OF status, reviewer_worker_id ON task_checks
WHEN NEW.status <> 'pending'
 AND NEW.reviewer_worker_id IS NOT NULL
 AND EXISTS (
     SELECT 1 FROM tasks t
     WHERE t.id = NEW.task_id AND trim(t.owner) = trim(NEW.reviewer_worker_id)
 )
BEGIN
    SELECT RAISE(ABORT, 'implementation owner cannot perform assurance or control review');
END;

CREATE TRIGGER IF NOT EXISTS specialist_role_assurance_sync_insert
AFTER INSERT ON specialist_roles
WHEN NEW.active = 1
BEGIN
    INSERT OR IGNORE INTO task_checks(
        id, task_id, check_type, criterion, specialist_role_id, required, created_at, updated_at
    )
    SELECT t.id || '-assurance-' || NEW.id, t.id, 'assurance',
           'baseline assurance participation', NEW.id, 1, unixepoch(), unixepoch()
    FROM tasks t JOIN task_states s ON s.id = t.state_id
    WHERE s.assurance_on_entry = 1 AND s.terminal = 0;
END;

CREATE TRIGGER IF NOT EXISTS specialist_role_assurance_sync_activate
AFTER UPDATE OF active ON specialist_roles
WHEN NEW.active = 1 AND OLD.active = 0
BEGIN
    INSERT OR IGNORE INTO task_checks(
        id, task_id, check_type, criterion, specialist_role_id, required, created_at, updated_at
    )
    SELECT t.id || '-assurance-' || NEW.id, t.id, 'assurance',
           'baseline assurance participation', NEW.id, 1, unixepoch(), unixepoch()
    FROM tasks t JOIN task_states s ON s.id = t.state_id
    WHERE s.assurance_on_entry = 1 AND s.terminal = 0;
END;

CREATE TRIGGER IF NOT EXISTS task_demand_guard
BEFORE INSERT ON tasks
BEGIN
    SELECT CASE WHEN NEW.parallelism='serial' AND
        (NEW.min_workers <> 1 OR NEW.target_workers <> 1 OR NEW.max_workers <> 1 OR json_array_length(NEW.work_units_json) <> 0)
        THEN RAISE(ABORT, 'serial worker demand must be exactly one worker with no work units') END;
    SELECT CASE WHEN NEW.parallelism IN ('partitionable', 'fan-out') AND
        json_array_length(NEW.work_units_json) < NEW.max_workers
        THEN RAISE(ABORT, 'parallel worker demand cannot exceed work units') END;
END;

CREATE TRIGGER IF NOT EXISTS task_demand_update_guard
BEFORE UPDATE OF parallelism, min_workers, target_workers, max_workers, work_units_json ON tasks
BEGIN
    SELECT CASE WHEN NEW.parallelism='serial' AND
        (NEW.min_workers <> 1 OR NEW.target_workers <> 1 OR NEW.max_workers <> 1 OR json_array_length(NEW.work_units_json) <> 0)
        THEN RAISE(ABORT, 'serial worker demand must be exactly one worker with no work units') END;
    SELECT CASE WHEN NEW.parallelism IN ('partitionable', 'fan-out') AND
        json_array_length(NEW.work_units_json) < NEW.max_workers
        THEN RAISE(ABORT, 'parallel worker demand cannot exceed work units') END;
END;

INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');

INSERT OR IGNORE INTO task_states(id, name, position, wip_limit, required_fields_json, terminal)
VALUES
    ('backlog', 'Backlog', 10, NULL, '["summary"]', 0),
    ('ready', 'Ready', 20, NULL, '["scope","owner","acceptance","validation"]', 0),
    ('active', 'Active', 30, 3, '["plan","worker"]', 0),
    ('review', 'Review', 40, 2, '["completion","evidence"]', 0),
    ('done', 'Done', 50, NULL, '["accepted_checks"]', 1);

UPDATE task_states SET assurance_on_entry = 1 WHERE id IN ('ready', 'review', 'done');
UPDATE task_states SET worker_entry = 1 WHERE id = 'active';
UPDATE task_states SET review_queue = 1 WHERE id = 'review';
UPDATE task_states SET requires_checks = 1, requires_evidence = 1 WHERE id = 'done';

UPDATE task_states SET previous_state_id = 'backlog', next_state_id = 'active'
    WHERE id = 'ready' AND previous_state_id IS NULL AND next_state_id IS NULL;
UPDATE task_states SET previous_state_id = 'ready', next_state_id = 'review'
    WHERE id = 'active' AND previous_state_id IS NULL AND next_state_id IS NULL;
UPDATE task_states SET previous_state_id = 'active', next_state_id = 'done'
    WHERE id = 'review' AND previous_state_id IS NULL AND next_state_id IS NULL;
UPDATE task_states SET previous_state_id = 'review'
    WHERE id = 'done' AND previous_state_id IS NULL;
UPDATE task_states SET next_state_id = 'ready'
    WHERE id = 'backlog' AND next_state_id IS NULL;

INSERT OR IGNORE INTO specialist_roles(id, name, purpose, description, created_at, updated_at)
VALUES
 ('workflow-governance','Workflow governance','Durable coordination and control','Evaluate workflow integrity, authority, and closure.',unixepoch(),unixepoch()),
 ('software-product-discovery','Software product discovery','Intent and outcome quality','Evaluate user problem, scope, and outcome alignment.',unixepoch(),unixepoch()),
 ('software-architecture','Software architecture','Design quality','Evaluate boundaries, contracts, and quality attributes.',unixepoch(),unixepoch()),
 ('software-delivery','Software delivery','Implementation quality','Evaluate implementation correctness and delivery evidence.',unixepoch(),unixepoch()),
 ('software-supply-chain','Software supply chain','Dependency and provenance risk','Evaluate third-party and build-input risk.',unixepoch(),unixepoch()),
 ('security-privacy-compliance','Security, privacy, and compliance','Security and control assurance','Evaluate security, privacy, and compliance implications.',unixepoch(),unixepoch()),
 ('production-operations','Production operations','Operational readiness','Evaluate observability, recovery, and operational safety.',unixepoch(),unixepoch()),
 ('systems-compatibility','Systems compatibility','Target-environment compatibility','Evaluate platform and runtime compatibility.',unixepoch(),unixepoch()),
 ('systems-diagnostics','Systems diagnostics','Evidence and diagnosis','Evaluate diagnostic quality and discriminating evidence.',unixepoch(),unixepoch()),
 ('code-conventions','Code conventions','Local style and maintainability','Evaluate adherence to repository conventions.',unixepoch(),unixepoch()),
 ('change-record-quality','Change record quality','Traceable change quality','Evaluate change rationale, proof, and handoff quality.',unixepoch(),unixepoch());
