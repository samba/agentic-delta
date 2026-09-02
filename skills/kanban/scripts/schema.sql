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

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    intent_id TEXT REFERENCES intents(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    default_option TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    answer TEXT,
    rationale TEXT,
    decided_by TEXT,
    impact TEXT,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER,
    CHECK (status IN ('open', 'resolved', 'withdrawn'))
);

CREATE INDEX IF NOT EXISTS decisions_status_idx ON decisions(status);
CREATE INDEX IF NOT EXISTS decisions_intent_idx ON decisions(intent_id);
CREATE INDEX IF NOT EXISTS decisions_task_idx ON decisions(task_id);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    intent_id TEXT REFERENCES intents(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    worker TEXT,
    lease_expires_at INTEGER,
    heartbeat_at INTEGER,
    checkpoint TEXT,
    cancellation_requested_at INTEGER,
    cancellation_acknowledged_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (status IN ('active', 'paused', 'cancelled', 'complete', 'failed')),
    CHECK (intent_id IS NOT NULL OR task_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS runs_task_idx ON runs(task_id);
CREATE INDEX IF NOT EXISTS runs_intent_idx ON runs(intent_id);

CREATE TABLE IF NOT EXISTS run_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    worker TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    state TEXT NOT NULL CHECK (state IN ('working', 'waiting', 'blocked', 'stalled', 'complete')),
    heartbeat_at INTEGER NOT NULL,
    progress_at INTEGER,
    progress_summary TEXT NOT NULL,
    next_action TEXT,
    expected_next_at INTEGER,
    blocker TEXT,
    evidence TEXT,
    idempotency_key TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE (run_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS run_checkins_run_idx ON run_checkins(run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS run_checkins_state_idx ON run_checkins(state, created_at DESC);

CREATE TABLE IF NOT EXISTS autonomy_envelopes (
    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    policy_json TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_types (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

INSERT OR IGNORE INTO gate_types(id, description) VALUES
('product-contract', 'Product contract is evidence-backed and decision-complete'),
('research-readiness', 'Research is sufficient and attributable'),
('assurance-readiness', 'Proactive specialist constraints and quality contributions are complete'),
('architecture', 'Architecture decisions and fitness checks are accepted'),
('design-validation', 'Design independently satisfies its scenarios'),
('implementation-verification', 'Implementation has revision-bound proof'),
('security', 'Applicable security concerns are resolved'),
('security-design', 'Design-time security concerns are resolved'),
('security-release', 'Release-time security evidence is accepted'),
('supply-chain', 'Supply-chain risks and evidence are resolved'),
('systems-compatibility', 'Target-system compatibility is proven'),
('code-style', 'Applicable project conventions are satisfied'),
('diagnosis', 'Diagnostic conclusions have discriminating evidence'),
('independent-review', 'An independent evaluator accepts the artifact'),
('delivery', 'Delivery controls and authorization are satisfied'),
('production-readiness', 'Operational readiness is accepted'),
('operational-observation', 'Post-delivery outcomes are observed');

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    gate_type TEXT NOT NULL,
    applicability TEXT NOT NULL DEFAULT 'applicable',
    recommendation TEXT NOT NULL DEFAULT 'pending',
    execution_status TEXT NOT NULL DEFAULT 'pending',
    evaluator TEXT,
    independent INTEGER NOT NULL DEFAULT 0,
    rework_destination TEXT,
    rationale TEXT,
    updated_at INTEGER NOT NULL,
    CHECK (applicability IN ('applicable', 'not-applicable', 'undetermined')),
    CHECK (recommendation IN ('pending', 'pass', 'fail', 'blocked', 'not-applicable')),
    CHECK (execution_status IN ('pending', 'complete', 'rework', 'blocked', 'not-applicable', 'budget-exhausted', 'authorization-required')),
    CHECK (recommendation != 'pass' OR (applicability = 'applicable' AND execution_status = 'complete')),
    CHECK (recommendation != 'fail' OR execution_status = 'rework'),
    CHECK (recommendation != 'blocked' OR execution_status = 'blocked'),
    CHECK (applicability != 'not-applicable' OR (
        recommendation = 'not-applicable' AND
        execution_status = 'not-applicable' AND
        length(trim(COALESCE(rationale, ''))) > 0
    ))
);

CREATE INDEX IF NOT EXISTS gates_task_idx ON gates(task_id);

CREATE TABLE IF NOT EXISTS specialist_classes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    role_context TEXT NOT NULL,
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS specialist_class_versions (
    specialist_class_id TEXT NOT NULL REFERENCES specialist_classes(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    title TEXT NOT NULL,
    role_context TEXT NOT NULL,
    description TEXT,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (specialist_class_id, version)
);

-- Portable default expertise. These are specialist roles, not skill-package
-- bindings. Reapplying the schema preserves project-local replacements.
INSERT OR IGNORE INTO specialist_classes(
    id, title, role_context, description, version, active, created_at, updated_at
) VALUES
('workflow-governance', 'Autonomous workflow governance specialist', 'You are an autonomous workflow governance specialist. Evaluate durable intent, backlog readiness, decision ownership, bounded delegation, autonomy envelopes, state transitions, evidence traceability, gate completeness, rework routing, and closure criteria. Return violated invariants, affected records, and the smallest safe correction. Do not perform domain review, move workflow state, expand permissions, accept risk, or authorize delivery.', 'Use for durable coordination, constrained-autonomy, traceability, and gate-conformance review.', 1, 1, unixepoch(), unixepoch()),
('workflow-learning', 'Workflow learning and metrics specialist', 'You are a workflow learning and metrics specialist. Analyze revision-linked outcomes, corrections, flow and quality metrics, costs, failures, overrides, and repeated mechanisms over a defined window. Separate observations from inferences, project lessons from reusable method changes, and correlation from causation. Return reproducible queries, evidence, candidate improvements, evaluation, and rollback conditions. Do not rewrite history, optimize a metric in isolation, change policy, move work, or promote your own recommendation.', 'Use for learning-ledger analysis, retrospectives, trends, and evidence-gated method improvement.', 1, 1, unixepoch(), unixepoch()),
('software-product-discovery', 'Software product discovery specialist', 'You are a software product discovery specialist. Establish users, problems, contexts, alternatives, workflows, measurable outcomes, constraints, non-goals, quality attributes, accessibility, and the smallest viable learning slices. Research established and open-source options, label hypotheses, and return a traceable product contract with unresolved human decisions. Do not fabricate user evidence, select architecture prematurely, implement code, accept risk, or authorize spending or launch.', 'Use for evidence-backed definition of a new product or major capability.', 1, 1, unixepoch(), unixepoch()),
('software-architecture', 'Software architecture specialist', 'You are a software architecture specialist. Evaluate requirement fit, reuse candidates, system and trust boundaries, interfaces, data and consistency models, failure and recovery behavior, evolution, deployment implications, and quality-attribute tradeoffs. Return compared alternatives, attributable research, decisions, architecture slices, fitness checks, and residual risks. Prefer proven maintained solutions where they fit and require a demonstrated gap for custom mechanisms. Do not change the product contract, implement the whole system, accept exceptions, or authorize release.', 'Use for system design after product requirements are sufficiently clear.', 1, 1, unixepoch(), unixepoch()),
('software-delivery', 'Software delivery and implementation quality specialist', 'You are a software delivery and implementation quality specialist. Produce or assess a bounded implementation against accepted requirements and architecture, repository conventions, dependency constraints, migrations, failure behavior, and risk-selected tests. Return changed artifacts, criterion-to-proof mapping, exact revision, reproducible validation, omissions, rollback information, and design drift. Research established solutions before adding custom mechanisms. Do not redefine requirements or architecture, overwrite unrelated work, accept residual risk, or approve release.', 'Use for bounded implementation, verification, maintainability, and releasable engineering handoffs.', 1, 1, unixepoch(), unixepoch()),
('software-supply-chain', 'Software supply-chain specialist', 'You are a software supply-chain specialist. Evaluate direct and transitive dependencies, build inputs, images, actions, generated artifacts, models, and services for canonical source, provenance, license, maintenance, vulnerabilities, immutable pinning, SBOM coverage, update ownership, and replacement risk. Return attributable evidence, unresolved obligations, and monitoring or replacement actions. Do not provide legal advice, accept business risk, change architecture, authorize purchase, or release artifacts.', 'Use for third-party and generated software selection, change, packaging, or release.', 1, 1, unixepoch(), unixepoch()),
('security-privacy-compliance', 'Security, privacy, and compliance specialist', 'You are a systems, application, privacy, and compliance security specialist. Evaluate assets, data classes and lifecycle, identities, authorization, trust boundaries, abuse cases, secrets, cryptography, tenancy, logging, third parties, deterministic controls, control evidence, and applicable assurance obligations. Return threat or control findings, proof gaps, residual risks, and the earliest repair stage. Do not certify compliance, give legal advice, accept residual risk, expand permissions, or authorize release.', 'Use for design-time or pre-release security, privacy, trust, audit, and compliance review.', 1, 1, unixepoch(), unixepoch()),
('production-operations', 'Production operations and reliability specialist', 'You are a production operations and reliability specialist. Evaluate user-centred service objectives, observability, actionable alerting, capacity, dependency failure, cost, deployment safety, configuration and secrets, migrations, rollback, backup and restore, disaster recovery, incident and support ownership, runbooks, launch controls, and post-launch evidence. Return reproducible operational proof, missing ownership, stop conditions, and residual risks. Do not impose an always-on service model without need, promise an SLA, accept risk, or authorize launch.', 'Use for staging, launch, production readiness, reliability, recovery, and sustained operation.', 1, 1, unixepoch(), unixepoch()),
('systems-compatibility', 'Systems compatibility and platform specialist', 'You are a systems compatibility and platform specialist. Derive constraints from the actual operating systems, distributions, architectures, runtimes, tools, orchestration versions, manifests, and rendered artifacts consumed by each target. Research platform-native and maintained solutions, then return a support matrix, exact commands or configuration, compatibility evidence, upgrade and rollback behavior, and unresolved version constraints. Do not guess portability, redesign the product, broaden machine access, mutate production, or authorize release.', 'Use when correctness depends on specific platform, runtime, deployment, or tool versions.', 1, 1, unixepoch(), unixepoch()),
('systems-diagnostics', 'Systems diagnostic specialist', 'You are a systems diagnostic specialist. Recover confidence from ambiguous or contradictory runtime evidence by bounding impact and authority, establishing a known-good witness, inspecting the artifact actually consumed, separating observations from assumptions, ranking falsifiable hypotheses, and running the cheapest discriminating probes. Return compared evidence, eliminated explanations, confidence, and the smallest supported remedy. Do not turn noisy instrumentation into certainty, run unbounded retries, remove valuable behavior merely to simplify diagnosis, or mutate live systems without authority.', 'Use when known-good and failing runtime evidence conflict or instrumentation is ambiguous.', 1, 1, unixepoch(), unixepoch()),
('code-conventions', 'Code conventions specialist', 'You are a code conventions specialist. Infer language-scoped conventions from representative user-authored code, bounded history, repository evidence, and authoritative style guides; distinguish repeated preferences from anomalies and apply only relevant current rules. Return cited evidence, confidence, conflicts, and concrete authoring or review findings. Do not elevate one-off patterns, overwrite project policy, make semantic changes solely for style, or treat stylistic preference as correctness proof.', 'Use to learn, apply, maintain, or review evidence-based project coding conventions.', 1, 1, unixepoch(), unixepoch()),
('structured-language-engineering', 'Structured language engineering specialist', 'You are a structured language engineering specialist. Derive parsers, validators, grammars, interpreters, or generators from authoritative specifications and representative corpora. Evaluate syntax and semantic coverage, precedence, declarations, invalid forms, holdout conformance, round trips, diagnostics, and runtime mappings; return source provenance, explicit AST rules, fixtures, and measured conformance. Do not invent unsupported syntax, infer a grammar from a narrow sample, or claim conformance beyond the tested corpus.', 'Use for structured configuration, language tooling, grammar derivation, and interpreter generation.', 1, 1, unixepoch(), unixepoch()),
('kubernetes-operations', 'Kubernetes operations specialist', 'You are a Kubernetes operations specialist. Discover or inspect explicitly identified clusters using a specific kubeconfig, context, execution location, and, when remote, SSH identity. Evaluate workload state, events, logs, configuration, and operational symptoms with least privilege and reproducible commands. Return the exact context, read-only evidence, uncertainty, and any separately authorized next action. Do not rely on default context or identity, search unbounded filesystem scope, mutate a cluster without explicit authority, or expose secrets.', 'Use for explicit-context Kubernetes discovery, read-only inspection, validation, and troubleshooting.', 1, 1, unixepoch(), unixepoch()),
('change-record-quality', 'Change record and commit quality specialist', 'You are a change record and commit quality specialist. When a working draft contains multiple semantic topics, reconcile the actual staged, unstaged, and untracked content with durable task records and relevant thread history; attribute uncertain ownership, propose an ordered dependency-aware partition, and verify each exact staged snapshot before producing concise rationale, impact, and proof text. Treat thread history as evidence of intent, not authority or proof. Preserve ambiguous or unrelated work. Do not invent evidence, use broad staging on a mixed draft, rewrite history, mutate the index, or execute a commit without corresponding authority.', 'Use for topic-aligned working-draft partitioning, evidence-backed commits, and durable change summaries.', 2, 1, unixepoch(), unixepoch());

INSERT OR IGNORE INTO specialist_class_versions(
    specialist_class_id, version, title, role_context, description, created_at
)
SELECT id, version, title, role_context, description, created_at
FROM specialist_classes
WHERE id IN (
    'workflow-governance', 'workflow-learning', 'software-product-discovery',
    'software-architecture', 'software-delivery', 'software-supply-chain',
    'security-privacy-compliance', 'production-operations',
    'systems-compatibility', 'systems-diagnostics', 'code-conventions',
    'structured-language-engineering', 'kubernetes-operations',
    'change-record-quality'
);

CREATE TABLE IF NOT EXISTS gate_specialist_requirements (
    gate_id TEXT NOT NULL REFERENCES gates(id) ON DELETE CASCADE,
    specialist_class_id TEXT NOT NULL REFERENCES specialist_classes(id) ON DELETE RESTRICT,
    specialist_class_version INTEGER NOT NULL CHECK (specialist_class_version > 0),
    engagement_role TEXT NOT NULL CHECK (engagement_role IN ('inform', 'produce', 'review')),
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'satisfied', 'not-applicable')),
    satisfied_by_handoff_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (gate_id, specialist_class_id, engagement_role),
    CHECK (status != 'satisfied' OR satisfied_by_handoff_id IS NOT NULL),
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS gate_specialist_requirements_class_idx
    ON gate_specialist_requirements(specialist_class_id, status);

CREATE TABLE IF NOT EXISTS work_types (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

INSERT OR IGNORE INTO work_types(id, title) VALUES
('product-discovery', 'Product discovery'),
('architecture-design', 'Architecture and design'),
('implementation', 'Software implementation'),
('data-migration', 'Data or schema migration'),
('infrastructure', 'Infrastructure or deployment configuration'),
('documentation', 'Documentation'),
('release', 'Release and launch'),
('operational-change', 'Operational change'),
('incident-diagnosis', 'Incident diagnosis'),
('existing-codebase-review', 'Existing codebase review against project goals'),
('workflow-reflection', 'Workflow reflection and improvement');

CREATE TABLE IF NOT EXISTS task_work_profiles (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    work_type_id TEXT NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT,
    lifecycle_stage TEXT NOT NULL CHECK (lifecycle_stage IN ('Discover', 'Design', 'Implement', 'Verify', 'Deliver', 'Observe')),
    scope_hash TEXT NOT NULL,
    artifact_kinds_json TEXT NOT NULL CHECK (json_valid(artifact_kinds_json) AND json_type(artifact_kinds_json) = 'array'),
    risk_attributes_json TEXT NOT NULL CHECK (json_valid(risk_attributes_json) AND json_type(risk_attributes_json) = 'array'),
    classified_by TEXT NOT NULL,
    rationale TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS review_policies (
    id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
    created_at INTEGER NOT NULL,
    PRIMARY KEY (id, version)
);

INSERT OR IGNORE INTO review_policies(id, version, title, status, created_at)
VALUES('standard-excellence', 1, 'Standard assurance and control policy', 'active', unixepoch());

CREATE TABLE IF NOT EXISTS review_policy_rules (
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    id TEXT NOT NULL,
    work_type_id TEXT REFERENCES work_types(id) ON DELETE RESTRICT,
    lifecycle_stage TEXT CHECK (lifecycle_stage IS NULL OR lifecycle_stage IN ('Discover', 'Design', 'Implement', 'Verify', 'Deliver', 'Observe')),
    specialist_class_id TEXT REFERENCES specialist_classes(id) ON DELETE RESTRICT,
    purpose TEXT NOT NULL CHECK (purpose IN ('assurance', 'control')),
    disposition TEXT NOT NULL CHECK (disposition IN ('required', 'conditional', 'normally-not-applicable', 'reviewer-determined')),
    condition_json TEXT CHECK (condition_json IS NULL OR json_valid(condition_json)),
    rationale TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (policy_id, policy_version, id),
    FOREIGN KEY (policy_id, policy_version) REFERENCES review_policies(id, version) ON DELETE CASCADE
);

INSERT OR IGNORE INTO review_policy_rules(
    policy_id, policy_version, id, work_type_id, lifecycle_stage,
    specialist_class_id, purpose, disposition, condition_json, rationale, priority
) VALUES
('standard-excellence', 1, 'discovery-code-assurance', 'product-discovery', 'Discover', 'code-conventions', 'assurance', 'normally-not-applicable', NULL, 'Early discovery has no code-bearing artifact; reconsider if the scope introduces an SDK, DSL, generator, or repository convention.', 100),
('standard-excellence', 1, 'discovery-code-control', 'product-discovery', 'Discover', 'code-conventions', 'control', 'normally-not-applicable', NULL, 'There is no source code to inspect during early product discovery.', 100),
('standard-excellence', 1, 'design-code-assurance', 'architecture-design', 'Design', 'code-conventions', 'assurance', 'conditional', '{"artifact_kinds_any":["public-sdk","generated-code","dsl"]}', 'Code-convention assurance matters when design constrains code-generating or public developer surfaces.', 100),
('standard-excellence', 1, 'design-code-control', 'architecture-design', 'Design', 'code-conventions', 'control', 'normally-not-applicable', NULL, 'Architecture artifacts normally contain no implementation source to inspect.', 100),
('standard-excellence', 1, 'discovery-kubernetes-control', 'product-discovery', 'Discover', 'kubernetes-operations', 'control', 'normally-not-applicable', NULL, 'Cluster inspection is not a control review of an early product contract.', 100),
('standard-excellence', 1, 'documentation-language-control', 'documentation', NULL, 'structured-language-engineering', 'control', 'conditional', '{"artifact_kinds_any":["grammar","dsl","structured-config"]}', 'Language conformance review applies only when documentation defines or changes a structured language.', 100);

CREATE TABLE IF NOT EXISTS review_policy_rule_references (
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL,
    PRIMARY KEY (policy_id, policy_version, rule_id, reference_id),
    FOREIGN KEY (policy_id, policy_version, rule_id)
        REFERENCES review_policy_rules(policy_id, policy_version, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_plans (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    scope_hash TEXT NOT NULL,
    assurance_gate_id TEXT NOT NULL UNIQUE REFERENCES gates(id) ON DELETE RESTRICT,
    control_gate_id TEXT NOT NULL UNIQUE REFERENCES gates(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'frozen', 'stale', 'complete')),
    created_at INTEGER NOT NULL,
    frozen_at INTEGER,
    FOREIGN KEY (policy_id, policy_version) REFERENCES review_policies(id, version) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS review_plans_active_task_idx
    ON review_plans(task_id) WHERE status IN ('draft', 'frozen');

CREATE TABLE IF NOT EXISTS review_plan_items (
    id TEXT PRIMARY KEY,
    review_plan_id TEXT NOT NULL REFERENCES review_plans(id) ON DELETE CASCADE,
    gate_id TEXT NOT NULL REFERENCES gates(id) ON DELETE RESTRICT,
    specialist_class_id TEXT NOT NULL,
    specialist_class_version INTEGER NOT NULL CHECK (specialist_class_version > 0),
    purpose TEXT NOT NULL CHECK (purpose IN ('assurance', 'control')),
    engagement_role TEXT NOT NULL CHECK (engagement_role IN ('inform', 'review')),
    policy_disposition TEXT NOT NULL CHECK (policy_disposition IN ('required', 'conditional', 'normally-not-applicable', 'reviewer-determined')),
    applicability TEXT NOT NULL CHECK (applicability IN ('applicable', 'not-applicable', 'undetermined')),
    applicability_source TEXT NOT NULL CHECK (applicability_source IN ('invariant', 'policy', 'reviewer')),
    policy_rule_id TEXT,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'satisfied', 'not-applicable', 'blocked')),
    satisfied_by_handoff_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (review_plan_id, specialist_class_id, purpose),
    UNIQUE (gate_id, specialist_class_id, engagement_role),
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT,
    FOREIGN KEY (review_plan_id, policy_rule_id)
        REFERENCES review_plan_rule_bindings(review_plan_id, rule_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (purpose <> 'control' OR engagement_role = 'review'),
    CHECK (purpose <> 'assurance' OR engagement_role = 'inform'),
    CHECK (applicability_source <> 'reviewer' OR satisfied_by_handoff_id IS NOT NULL),
    CHECK (status NOT IN ('satisfied', 'not-applicable') OR satisfied_by_handoff_id IS NOT NULL OR applicability_source = 'policy'),
    CHECK (status <> 'not-applicable' OR applicability_source <> 'policy' OR policy_rule_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS review_plan_rule_bindings (
    review_plan_id TEXT NOT NULL REFERENCES review_plans(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    PRIMARY KEY (review_plan_id, rule_id),
    FOREIGN KEY (policy_id, policy_version, rule_id)
        REFERENCES review_policy_rules(policy_id, policy_version, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    gate_id TEXT REFERENCES gates(id) ON DELETE SET NULL,
    criterion_id TEXT NOT NULL,
    artifact TEXT NOT NULL,
    revision TEXT NOT NULL,
    probe TEXT NOT NULL,
    result TEXT NOT NULL,
    producer TEXT NOT NULL,
    environment TEXT,
    location TEXT,
    content_hash TEXT,
    created_at INTEGER NOT NULL,
    CHECK (result IN ('pass', 'fail', 'inconclusive'))
);

CREATE INDEX IF NOT EXISTS evidence_task_idx ON evidence(task_id);
CREATE INDEX IF NOT EXISTS evidence_gate_idx ON evidence(gate_id);

CREATE TABLE IF NOT EXISTS specialist_handoffs (
    id TEXT PRIMARY KEY,
    document_hash TEXT NOT NULL UNIQUE,
    contract_version TEXT NOT NULL CHECK (contract_version = '2'),
    specialist_class_id TEXT NOT NULL REFERENCES specialist_classes(id) ON DELETE RESTRICT,
    specialist_class_version INTEGER NOT NULL CHECK (specialist_class_version > 0),
    engagement_role TEXT NOT NULL CHECK (engagement_role IN ('inform', 'produce', 'review')),
    review_purpose TEXT CHECK (review_purpose IS NULL OR review_purpose IN ('assurance', 'control')),
    review_plan_item_id TEXT REFERENCES review_plan_items(id) ON DELETE RESTRICT,
    worker_id TEXT NOT NULL,
    gate_id TEXT REFERENCES gates(id) ON DELETE RESTRICT,
    intent_id TEXT REFERENCES intents(id) ON DELETE RESTRICT,
    task_id TEXT REFERENCES tasks(id) ON DELETE RESTRICT,
    run_id TEXT REFERENCES runs(id) ON DELETE RESTRICT,
    attempt_id TEXT,
    scope TEXT NOT NULL,
    applicability TEXT NOT NULL CHECK (applicability IN ('applicable', 'not-applicable', 'undetermined')),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('pass', 'fail', 'blocked', 'not-applicable')),
    execution_status TEXT NOT NULL CHECK (execution_status IN ('complete', 'rework', 'blocked', 'not-applicable', 'budget-exhausted', 'authorization-required')),
    independent INTEGER NOT NULL DEFAULT 0 CHECK (independent IN (0, 1)),
    rework_destination TEXT,
    created_at INTEGER NOT NULL,
    CHECK (task_id IS NOT NULL OR intent_id IS NOT NULL),
    CHECK (recommendation != 'pass' OR (applicability = 'applicable' AND execution_status = 'complete')),
    CHECK (recommendation != 'fail' OR execution_status = 'rework'),
    CHECK (recommendation != 'blocked' OR execution_status = 'blocked'),
    CHECK (recommendation != 'not-applicable' OR (applicability = 'not-applicable' AND execution_status = 'not-applicable')),
    CHECK (review_plan_item_id IS NULL OR review_purpose IS NOT NULL),
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS specialist_handoffs_task_idx ON specialist_handoffs(task_id);
CREATE INDEX IF NOT EXISTS specialist_handoffs_gate_idx ON specialist_handoffs(gate_id);

CREATE TRIGGER IF NOT EXISTS handoff_requirement_reference_check
BEFORE UPDATE OF satisfied_by_handoff_id ON gate_specialist_requirements
WHEN NEW.satisfied_by_handoff_id IS NOT NULL
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM specialist_handoffs h
        WHERE h.id = NEW.satisfied_by_handoff_id
          AND h.gate_id = NEW.gate_id
          AND h.specialist_class_id = NEW.specialist_class_id
          AND h.specialist_class_version = NEW.specialist_class_version
          AND h.engagement_role = NEW.engagement_role
    ) THEN RAISE(ABORT, 'handoff does not satisfy specialist requirement') END;
END;

CREATE TRIGGER IF NOT EXISTS specialist_requirement_resolution_guard
BEFORE UPDATE OF status, satisfied_by_handoff_id ON gate_specialist_requirements
WHEN NEW.status <> 'pending'
BEGIN
    SELECT CASE WHEN NEW.satisfied_by_handoff_id IS NULL
        THEN RAISE(ABORT, 'resolved specialist requirement needs a handoff') END;
END;

CREATE TABLE IF NOT EXISTS handoff_permissions (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (handoff_id, permission)
);

CREATE TABLE IF NOT EXISTS handoff_sources (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    reference_id TEXT REFERENCES research_references(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    url TEXT NOT NULL,
    retrieved_at TEXT,
    PRIMARY KEY (handoff_id, ordinal)
);

CREATE TABLE IF NOT EXISTS handoff_artifacts (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('observed', 'changed')),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    artifact_ref TEXT NOT NULL,
    revision TEXT,
    digest TEXT,
    PRIMARY KEY (handoff_id, kind, ordinal)
);

CREATE TABLE IF NOT EXISTS handoff_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    severity TEXT NOT NULL CHECK (severity IN ('blocker', 'required-follow-up', 'advisory')),
    summary TEXT NOT NULL,
    rework_destination TEXT,
    UNIQUE (handoff_id, ordinal)
);

CREATE TABLE IF NOT EXISTS handoff_evidence (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    PRIMARY KEY (handoff_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS handoff_risks (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    summary TEXT NOT NULL,
    owner TEXT,
    acceptance_required INTEGER NOT NULL CHECK (acceptance_required IN (0, 1)),
    PRIMARY KEY (handoff_id, ordinal)
);

CREATE TABLE IF NOT EXISTS handoff_decisions (
    handoff_id TEXT NOT NULL REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    question TEXT NOT NULL,
    authority_required INTEGER NOT NULL CHECK (authority_required IN (0, 1)),
    PRIMARY KEY (handoff_id, ordinal)
);

CREATE TABLE IF NOT EXISTS handoff_receipts (
    id TEXT PRIMARY KEY,
    handoff_id TEXT NOT NULL UNIQUE REFERENCES specialist_handoffs(id) ON DELETE CASCADE,
    document_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'committed'),
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS side_effect_receipts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    action_class TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    receipt TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE (run_id, idempotency_key),
    CHECK (status IN ('planned', 'applied', 'failed', 'compensated'))
);

CREATE TABLE IF NOT EXISTS principles (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS principles_theme_idx ON principles(theme);

-- Principles express durable outcomes. Tenets turn them into actionable,
-- scoped standard work. Frozen guidance snapshots then materialize the exact
-- tenet versions that governed a task; obligations prove how assurance changed
-- production rather than merely recording that a consultation occurred.
CREATE TABLE IF NOT EXISTS principle_versions (
    principle_id TEXT NOT NULL REFERENCES principles(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    statement TEXT NOT NULL,
    intended_outcome TEXT NOT NULL,
    scope_type TEXT NOT NULL DEFAULT 'suite' CHECK (scope_type IN ('suite', 'project')),
    authority_class TEXT NOT NULL CHECK (authority_class IN ('normative', 'methodological', 'local-policy', 'experimental')),
    rationale TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'superseded', 'retired')),
    effective_at INTEGER,
    superseded_at INTEGER,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (principle_id, version)
);

CREATE TABLE IF NOT EXISTS principle_references (
    principle_id TEXT NOT NULL REFERENCES principles(id) ON DELETE RESTRICT,
    principle_version INTEGER NOT NULL,
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL CHECK (relationship IN ('supports', 'qualifies', 'contradicts', 'supersedes')),
    interpretation TEXT NOT NULL,
    PRIMARY KEY (principle_id, principle_version, reference_id),
    FOREIGN KEY (principle_id, principle_version)
        REFERENCES principle_versions(principle_id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tenets (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    title TEXT NOT NULL,
    current_version INTEGER NOT NULL CHECK (current_version > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tenet_versions (
    tenet_id TEXT NOT NULL REFERENCES tenets(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    instruction TEXT NOT NULL,
    intended_effect TEXT NOT NULL,
    strength TEXT NOT NULL CHECK (strength IN ('required', 'advisory')),
    exception_authority TEXT NOT NULL CHECK (exception_authority IN ('policy', 'specialist', 'human')),
    verification_strategy TEXT NOT NULL,
    experiment_eligible INTEGER NOT NULL DEFAULT 1 CHECK (experiment_eligible IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'superseded', 'retired')),
    effective_at INTEGER,
    superseded_at INTEGER,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (tenet_id, version)
);

CREATE TABLE IF NOT EXISTS tenet_principles (
    tenet_id TEXT NOT NULL,
    tenet_version INTEGER NOT NULL,
    principle_id TEXT NOT NULL,
    principle_version INTEGER NOT NULL,
    PRIMARY KEY (tenet_id, tenet_version, principle_id, principle_version),
    FOREIGN KEY (tenet_id, tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE CASCADE,
    FOREIGN KEY (principle_id, principle_version) REFERENCES principle_versions(principle_id, version) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS tenet_references (
    tenet_id TEXT NOT NULL,
    tenet_version INTEGER NOT NULL,
    reference_id TEXT NOT NULL REFERENCES research_references(id) ON DELETE RESTRICT,
    relationship TEXT NOT NULL CHECK (relationship IN ('supports', 'qualifies', 'contradicts', 'supersedes')),
    interpretation TEXT NOT NULL,
    PRIMARY KEY (tenet_id, tenet_version, reference_id),
    FOREIGN KEY (tenet_id, tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tenet_applicability_rules (
    tenet_id TEXT NOT NULL,
    tenet_version INTEGER NOT NULL,
    id TEXT NOT NULL,
    work_type_id TEXT REFERENCES work_types(id) ON DELETE RESTRICT,
    lifecycle_stage TEXT CHECK (lifecycle_stage IS NULL OR lifecycle_stage IN ('Discover', 'Design', 'Implement', 'Verify', 'Deliver', 'Observe')),
    specialist_class_id TEXT REFERENCES specialist_classes(id) ON DELETE RESTRICT,
    condition_json TEXT CHECK (condition_json IS NULL OR json_valid(condition_json)),
    disposition TEXT NOT NULL CHECK (disposition IN ('required', 'advisory', 'normally-not-applicable', 'conditional')),
    rationale TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenet_id, tenet_version, id),
    FOREIGN KEY (tenet_id, tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_tenet_overrides (
    id TEXT PRIMARY KEY,
    tenet_id TEXT NOT NULL,
    tenet_version INTEGER NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('required', 'advisory', 'not-applicable', 'exception')),
    scope_json TEXT NOT NULL CHECK (json_valid(scope_json)),
    rationale TEXT NOT NULL,
    decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    authorized_by TEXT NOT NULL,
    effective_at INTEGER NOT NULL,
    expires_at INTEGER,
    rollback_condition TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (tenet_id, tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE RESTRICT,
    CHECK (disposition NOT IN ('not-applicable', 'exception') OR decision_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS guidance_snapshots (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    review_plan_id TEXT NOT NULL UNIQUE REFERENCES review_plans(id) ON DELETE RESTRICT,
    scope_hash TEXT NOT NULL,
    guidance_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'frozen', 'stale', 'complete')),
    created_at INTEGER NOT NULL,
    frozen_at INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS guidance_snapshots_active_task_idx
    ON guidance_snapshots(task_id) WHERE status IN ('draft', 'frozen');

CREATE TABLE IF NOT EXISTS guidance_snapshot_tenets (
    guidance_snapshot_id TEXT NOT NULL REFERENCES guidance_snapshots(id) ON DELETE CASCADE,
    tenet_id TEXT NOT NULL,
    tenet_version INTEGER NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('required', 'advisory', 'not-applicable', 'exception')),
    resolution TEXT NOT NULL CHECK (resolution IN ('pending', 'materialized', 'inherited', 'not-applicable', 'exception', 'blocked')),
    applicability_source TEXT NOT NULL CHECK (applicability_source IN ('tenet', 'policy', 'specialist', 'human')),
    rationale TEXT NOT NULL,
    override_id TEXT REFERENCES project_tenet_overrides(id) ON DELETE RESTRICT,
    resolved_by_handoff_id TEXT REFERENCES specialist_handoffs(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (guidance_snapshot_id, tenet_id),
    FOREIGN KEY (tenet_id, tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE RESTRICT,
    CHECK (resolution <> 'exception' OR applicability_source = 'human'),
    CHECK (resolution <> 'not-applicable' OR applicability_source IN ('policy', 'specialist', 'human'))
);

CREATE TABLE IF NOT EXISTS assurance_baselines (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('product', 'subsystem', 'architecture', 'environment')),
    scope_ref TEXT NOT NULL,
    premise_hash TEXT NOT NULL,
    guidance_hash TEXT NOT NULL,
    assumptions_json TEXT NOT NULL CHECK (json_valid(assumptions_json)),
    invalidation_json TEXT NOT NULL CHECK (json_valid(invalidation_json)),
    valid_until INTEGER,
    status TEXT NOT NULL CHECK (status IN ('active', 'stale', 'retired')),
    approved_by TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS assurance_obligations (
    id TEXT PRIMARY KEY,
    guidance_snapshot_id TEXT NOT NULL,
    tenet_id TEXT NOT NULL,
    review_plan_item_id TEXT REFERENCES review_plan_items(id) ON DELETE RESTRICT,
    baseline_id TEXT REFERENCES assurance_baselines(id) ON DELETE RESTRICT,
    obligation_type TEXT NOT NULL CHECK (obligation_type IN ('acceptance-criterion', 'design-constraint', 'decision', 'fitness-function', 'test', 'policy-control', 'delivery-safeguard', 'observability', 'operational-readiness', 'risk-disposition')),
    summary TEXT NOT NULL,
    affected_artifact TEXT,
    lifecycle_stage TEXT NOT NULL CHECK (lifecycle_stage IN ('Discover', 'Design', 'Implement', 'Verify', 'Deliver', 'Observe')),
    verification_method TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'satisfied', 'waived', 'blocked')),
    evidence_id TEXT REFERENCES evidence(id) ON DELETE RESTRICT,
    decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (guidance_snapshot_id, tenet_id)
        REFERENCES guidance_snapshot_tenets(guidance_snapshot_id, tenet_id) ON DELETE CASCADE,
    CHECK (status <> 'satisfied' OR evidence_id IS NOT NULL),
    CHECK (status <> 'waived' OR decision_id IS NOT NULL),
    CHECK (baseline_id IS NULL OR status IN ('planned', 'satisfied'))
);

CREATE TABLE IF NOT EXISTS improvement_experiments (
    id TEXT PRIMARY KEY,
    principle_id TEXT NOT NULL REFERENCES principles(id) ON DELETE RESTRICT,
    baseline_tenet_id TEXT NOT NULL,
    baseline_tenet_version INTEGER NOT NULL,
    variant_tenet_id TEXT NOT NULL,
    variant_tenet_version INTEGER NOT NULL,
    problem_statement TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    assignment_scope_json TEXT NOT NULL CHECK (json_valid(assignment_scope_json)),
    exclusions_json TEXT NOT NULL CHECK (json_valid(exclusions_json)),
    metrics_json TEXT NOT NULL CHECK (json_valid(metrics_json)),
    observation_start INTEGER,
    observation_end INTEGER,
    owner TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'running', 'evaluating', 'promoted', 'revised', 'rolled-back', 'cancelled')),
    outcome TEXT,
    rollback_condition TEXT NOT NULL,
    decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (baseline_tenet_id, baseline_tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE RESTRICT,
    FOREIGN KEY (variant_tenet_id, variant_tenet_version) REFERENCES tenet_versions(tenet_id, version) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS experiment_assignments (
    experiment_id TEXT NOT NULL REFERENCES improvement_experiments(id) ON DELETE RESTRICT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    arm TEXT NOT NULL CHECK (arm IN ('baseline', 'variant')),
    assigned_at INTEGER NOT NULL,
    PRIMARY KEY (experiment_id, task_id)
);

CREATE TABLE IF NOT EXISTS flow_constraints (
    id TEXT PRIMARY KEY,
    goal_ref TEXT NOT NULL,
    constraint_type TEXT NOT NULL CHECK (constraint_type IN ('resource', 'policy', 'capability', 'market', 'unknown')),
    constraint_ref TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    buffer_target REAL,
    buffer_current REAL,
    exploit_action TEXT NOT NULL,
    subordinate_action TEXT NOT NULL,
    elevate_action TEXT,
    owner TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'active', 'broken', 'superseded')),
    review_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_signals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    obligation_id TEXT REFERENCES assurance_obligations(id) ON DELETE RESTRICT,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('abnormality', 'escaped-defect', 'process-failure', 'constraint-starvation', 'constraint-overload')),
    severity TEXT NOT NULL CHECK (severity IN ('advisory', 'stop-affected-work', 'stop-value-stream')),
    summary TEXT NOT NULL,
    containment TEXT NOT NULL,
    occurrence_cause TEXT,
    escape_cause TEXT,
    systemic_cause TEXT,
    countermeasure TEXT,
    recurrence_test TEXT,
    owner TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'contained', 'resolved')),
    opened_at INTEGER NOT NULL,
    resolved_at INTEGER
);

CREATE TABLE IF NOT EXISTS project_specialist_enrollments (
    intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    specialist_class_id TEXT NOT NULL,
    specialist_class_version INTEGER NOT NULL CHECK (specialist_class_version > 0),
    status TEXT NOT NULL CHECK (status IN ('enrolled', 'consulted', 'not-applicable', 'retired')),
    rationale TEXT NOT NULL,
    enrolled_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (intent_id, specialist_class_id),
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS specialist_guidance_proposals (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    specialist_class_id TEXT NOT NULL,
    specialist_class_version INTEGER NOT NULL,
    handoff_id TEXT REFERENCES specialist_handoffs(id) ON DELETE RESTRICT,
    guidance_kind TEXT NOT NULL CHECK (guidance_kind IN ('principle', 'tenet')),
    theme TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    intended_outcome TEXT NOT NULL,
    rationale TEXT NOT NULL,
    applicability_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(applicability_json)),
    verification_strategy TEXT,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'accepted', 'rejected', 'superseded')),
    adopted_principle_id TEXT REFERENCES principles(id) ON DELETE RESTRICT,
    adopted_tenet_id TEXT REFERENCES tenets(id) ON DELETE RESTRICT,
    decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (intent_id, specialist_class_id)
        REFERENCES project_specialist_enrollments(intent_id, specialist_class_id) ON DELETE RESTRICT,
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT,
    CHECK (guidance_kind <> 'principle' OR verification_strategy IS NULL),
    CHECK (status <> 'accepted' OR adopted_principle_id IS NOT NULL OR adopted_tenet_id IS NOT NULL),
    CHECK (adopted_principle_id IS NULL OR guidance_kind = 'principle'),
    CHECK (adopted_tenet_id IS NULL OR guidance_kind = 'tenet')
);

CREATE TABLE IF NOT EXISTS bugs (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE RESTRICT,
    summary TEXT NOT NULL,
    observed_behavior TEXT NOT NULL,
    expected_behavior TEXT NOT NULL,
    reproduction TEXT,
    environment TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_json) AND json_type(evidence_json)='array'),
    reporter TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered', 'triaging', 'prioritized', 'actioned', 'resolved', 'deferred', 'rejected')),
    priority_rank INTEGER CHECK (priority_rank IS NULL OR priority_rank >= 0),
    priority_rationale TEXT,
    action_task_id TEXT UNIQUE REFERENCES tasks(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (status NOT IN ('prioritized', 'actioned', 'resolved', 'deferred') OR priority_rank IS NOT NULL),
    CHECK (status NOT IN ('actioned', 'resolved') OR action_task_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS bug_specialist_assessments (
    bug_id TEXT NOT NULL REFERENCES bugs(id) ON DELETE CASCADE,
    specialist_class_id TEXT NOT NULL,
    specialist_class_version INTEGER NOT NULL,
    applicability TEXT NOT NULL CHECK (applicability IN ('pending', 'applicable', 'not-applicable')),
    goal_impact INTEGER CHECK (goal_impact IS NULL OR goal_impact BETWEEN 0 AND 100),
    urgency INTEGER CHECK (urgency IS NULL OR urgency BETWEEN 0 AND 100),
    risk_summary TEXT,
    rationale TEXT,
    assessed_by TEXT,
    assessed_at INTEGER,
    PRIMARY KEY (bug_id, specialist_class_id),
    FOREIGN KEY (specialist_class_id, specialist_class_version)
        REFERENCES specialist_class_versions(specialist_class_id, version) ON DELETE RESTRICT,
    CHECK (applicability = 'pending' OR length(trim(COALESCE(rationale, ''))) > 0),
    CHECK (applicability <> 'applicable' OR (goal_impact IS NOT NULL AND urgency IS NOT NULL AND risk_summary IS NOT NULL AND assessed_by IS NOT NULL))
);

INSERT OR IGNORE INTO principles(id, theme, statement, status, raw_json, updated_at) VALUES
('built-in-quality', 'quality', 'Build quality into the production process instead of depending on downstream inspection.', 'active', '{"applies_to":["governed-work"],"exceptions":[],"id":"built-in-quality","statement":"Build quality into the production process instead of depending on downstream inspection.","status":"active"}', unixepoch()),
('optimize-value-flow', 'flow', 'Optimize end-to-end customer value and system throughput rather than local utilization.', 'active', '{"applies_to":["governed-work"],"exceptions":[],"id":"optimize-value-flow","statement":"Optimize end-to-end customer value and system throughput rather than local utilization.","status":"active"}', unixepoch()),
('improve-standard-work', 'learning', 'Improve a visible standard through evidence-backed experiments while preserving history and rollback.', 'active', '{"applies_to":["governed-work"],"exceptions":[],"id":"improve-standard-work","statement":"Improve a visible standard through evidence-backed experiments while preserving history and rollback.","status":"active"}', unixepoch());

INSERT OR IGNORE INTO principle_versions(principle_id, version, statement, intended_outcome, scope_type, authority_class, rationale, status, effective_at, created_at) VALUES
('built-in-quality', 1, 'Build quality into the production process instead of depending on downstream inspection.', 'A capable process prevents known defect classes and exposes abnormalities at their source.', 'suite', 'methodological', 'Lean jidoka and Deming quality-at-source guidance.', 'active', unixepoch(), unixepoch()),
('optimize-value-flow', 1, 'Optimize end-to-end customer value and system throughput rather than local utilization.', 'Work flows toward customer outcomes without avoidable queues, inventory, or constraint overload.', 'suite', 'methodological', 'Lean flow/pull and Theory of Constraints focusing guidance.', 'active', unixepoch(), unixepoch()),
('improve-standard-work', 1, 'Improve a visible standard through evidence-backed experiments while preserving history and rollback.', 'Learning produces controlled, measurable, reversible improvements to future work.', 'suite', 'methodological', 'Kaizen requires a current standard and disciplined experimentation.', 'active', unixepoch(), unixepoch());

INSERT OR IGNORE INTO tenets(id, theme, title, current_version, active, created_at, updated_at) VALUES
('assurance-becomes-work', 'quality', 'Translate assurance into production obligations', 1, 1, unixepoch(), unixepoch()),
('fast-feedback-at-source', 'quality', 'Use fast feedback at the point of creation', 1, 1, unixepoch(), unixepoch()),
('stop-on-abnormality', 'quality', 'Stop propagation of known abnormalities', 1, 1, unixepoch(), unixepoch()),
('manage-system-constraint', 'flow', 'Manage the current system constraint', 1, 1, unixepoch(), unixepoch()),
('experiment-from-standard', 'learning', 'Improve tenets through controlled experiments', 1, 1, unixepoch(), unixepoch());

INSERT OR IGNORE INTO tenet_versions(tenet_id, version, instruction, intended_effect, strength, exception_authority, verification_strategy, experiment_eligible, status, effective_at, created_at) VALUES
('assurance-becomes-work', 1, 'Convert every material assurance finding into an attributable production obligation, authorized rejection, or evidenced not-applicable disposition before substantive work.', 'Specialist knowledge changes how the artifact is produced.', 'required', 'specialist', 'Inspect the frozen guidance snapshot and its linked obligations and dispositions.', 0, 'active', unixepoch(), unixepoch()),
('fast-feedback-at-source', 1, 'Select the earliest practical deterministic check for each material obligation and run it while producing the artifact.', 'Routine defects are prevented or exposed before downstream control review.', 'required', 'specialist', 'Verify obligations name reproducible point-of-creation checks and revision-bound evidence.', 1, 'active', unixepoch(), unixepoch()),
('stop-on-abnormality', 1, 'Contain a material abnormality, stop affected downstream work, and record occurrence, escape, and systemic causes before resuming.', 'Known defects and invalid assumptions do not propagate.', 'required', 'human', 'Verify an open quality signal blocks affected completion and has containment and recurrence evidence.', 0, 'active', unixepoch(), unixepoch()),
('manage-system-constraint', 1, 'Identify the current constraint and subordinate dispatch and WIP decisions to end-to-end flow rather than local utilization.', 'The system avoids feeding inventory into its limiting queue.', 'advisory', 'policy', 'Review constraint evidence, buffer state, and exploit/subordinate/elevate actions.', 1, 'active', unixepoch(), unixepoch()),
('experiment-from-standard', 1, 'Change governing tenets only through a scoped hypothesis, baseline, measures, safety exclusions, review, and rollback decision.', 'Kaizen improves a known standard without losing causal or historical context.', 'required', 'human', 'Verify experiment assignment, outcome measures, decision, and versioned promotion or rollback.', 0, 'active', unixepoch(), unixepoch());

INSERT OR IGNORE INTO tenet_principles(tenet_id, tenet_version, principle_id, principle_version) VALUES
('assurance-becomes-work', 1, 'built-in-quality', 1),
('fast-feedback-at-source', 1, 'built-in-quality', 1),
('stop-on-abnormality', 1, 'built-in-quality', 1),
('manage-system-constraint', 1, 'optimize-value-flow', 1),
('experiment-from-standard', 1, 'improve-standard-work', 1);

CREATE TABLE IF NOT EXISTS learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    context_track TEXT NOT NULL DEFAULT 'execution',
    outcome TEXT,
    reason_summary TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    storage_class TEXT NOT NULL DEFAULT 'database',
    redaction_state TEXT NOT NULL DEFAULT 'redacted',
    intent_id TEXT REFERENCES intents(id) ON DELETE SET NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    decision_id TEXT REFERENCES decisions(id) ON DELETE SET NULL,
    gate_id TEXT REFERENCES gates(id) ON DELETE SET NULL,
    evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
    reference_id TEXT REFERENCES research_references(id) ON DELETE SET NULL,
    attempt_id TEXT,
    artifact_ref TEXT,
    commit_ref TEXT,
    reviewer_id TEXT,
    source_task_event_id INTEGER UNIQUE REFERENCES task_events(event_id) ON DELETE SET NULL,
    CHECK (context_track IN ('execution', 'reflection')),
    CHECK (storage_class IN ('database', 'external-artifact')),
    CHECK (redaction_state IN ('redacted', 'not-sensitive', 'needs-review'))
);

CREATE INDEX IF NOT EXISTS learning_events_time_idx ON learning_events(occurred_at);
CREATE INDEX IF NOT EXISTS learning_events_task_idx ON learning_events(task_id);
CREATE INDEX IF NOT EXISTS learning_events_intent_idx ON learning_events(intent_id);
CREATE INDEX IF NOT EXISTS learning_events_run_idx ON learning_events(run_id);
CREATE INDEX IF NOT EXISTS learning_events_type_idx ON learning_events(event_type);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at INTEGER NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL DEFAULT '',
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    unit TEXT NOT NULL,
    window_start INTEGER,
    window_end INTEGER,
    derivation_version TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (measured_at, scope_type, scope_id, metric_name, derivation_version)
);

CREATE INDEX IF NOT EXISTS metric_snapshots_name_time_idx
    ON metric_snapshots(metric_name, measured_at);

CREATE TABLE IF NOT EXISTS learning_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    event_start_id INTEGER,
    event_end_id INTEGER,
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    artifact_location TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    preserved_signal TEXT NOT NULL,
    dropped_detail TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS learning_archives_hash_idx
    ON learning_archives(content_hash);

CREATE TRIGGER IF NOT EXISTS task_event_to_learning_event
AFTER INSERT ON task_events
BEGIN
    INSERT OR IGNORE INTO learning_events(
        occurred_at, event_type, reason_summary, task_id, source_task_event_id
    ) VALUES(NEW.created_at, NEW.event_type, NEW.message, NEW.task_id, NEW.event_id);
END;

CREATE TRIGGER IF NOT EXISTS run_to_learning_event
AFTER INSERT ON runs
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, reason_summary, intent_id, task_id, run_id)
    VALUES(NEW.created_at, 'run.started', 'run started', NEW.intent_id, NEW.task_id, NEW.id);
END;

CREATE TRIGGER IF NOT EXISTS envelope_to_learning_event
AFTER INSERT ON autonomy_envelopes
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, reason_summary, run_id)
    VALUES(NEW.created_at, 'authorization.envelope', 'immutable autonomy envelope issued', NEW.run_id);
END;

CREATE TRIGGER IF NOT EXISTS gate_to_learning_event
AFTER INSERT ON gates
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, task_id, gate_id)
    VALUES(NEW.updated_at, 'gate.required', NEW.recommendation, NEW.gate_type, NEW.task_id, NEW.id);
END;

CREATE TRIGGER IF NOT EXISTS gate_update_to_learning_event
AFTER UPDATE OF recommendation ON gates
WHEN OLD.recommendation <> NEW.recommendation
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, task_id, gate_id, reviewer_id)
    VALUES(NEW.updated_at, 'gate.result', NEW.recommendation, NEW.gate_type, NEW.task_id, NEW.id, NEW.evaluator);
END;

CREATE TRIGGER IF NOT EXISTS evidence_to_learning_event
AFTER INSERT ON evidence
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, task_id, gate_id, evidence_id, artifact_ref)
    VALUES(NEW.created_at, 'evidence.recorded', NEW.result, NEW.criterion_id, NEW.task_id, NEW.gate_id, NEW.id, NEW.artifact);
END;

CREATE TRIGGER IF NOT EXISTS receipt_to_learning_event
AFTER INSERT ON side_effect_receipts
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, run_id, artifact_ref)
    VALUES(NEW.created_at, 'side-effect.receipt', NEW.status, NEW.action_class, NEW.run_id, NEW.target);
END;

CREATE TRIGGER IF NOT EXISTS decision_to_learning_event
AFTER INSERT ON decisions
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, intent_id, task_id, decision_id)
    VALUES(NEW.created_at, 'decision.opened', NEW.status, NEW.question, NEW.intent_id, NEW.task_id, NEW.id);
END;

CREATE TRIGGER IF NOT EXISTS enroll_specialists_for_new_project
AFTER INSERT ON intents
BEGIN
    INSERT INTO project_specialist_enrollments(
        intent_id, specialist_class_id, specialist_class_version, status,
        rationale, enrolled_at, updated_at
    )
    SELECT NEW.id, id, version, 'enrolled',
           'Default early enrollment: establish project guidance and review work against the goal.',
           NEW.created_at, NEW.created_at
    FROM specialist_classes WHERE active=1;
END;

DROP TRIGGER IF EXISTS enroll_new_specialist_in_open_projects;
CREATE TRIGGER enroll_new_specialist_in_open_projects
AFTER INSERT ON specialist_class_versions
WHEN EXISTS (
    SELECT 1 FROM specialist_classes c
    WHERE c.id=NEW.specialist_class_id AND c.active=1 AND c.version=NEW.version
)
BEGIN
    INSERT OR IGNORE INTO project_specialist_enrollments(
        intent_id, specialist_class_id, specialist_class_version, status,
        rationale, enrolled_at, updated_at
    )
    SELECT i.id, NEW.specialist_class_id, NEW.version, 'enrolled',
           'Specialist class added after project capture; early enrollment backfilled.',
           NEW.created_at, NEW.created_at
    FROM intents i WHERE i.state <> 'closed';
END;

CREATE TRIGGER IF NOT EXISTS bug_seed_specialist_assessments
AFTER INSERT ON bugs
BEGIN
    INSERT INTO bug_specialist_assessments(
        bug_id, specialist_class_id, specialist_class_version, applicability
    )
    SELECT NEW.id, e.specialist_class_id, e.specialist_class_version, 'pending'
    FROM project_specialist_enrollments e
    WHERE e.intent_id=NEW.intent_id AND e.status IN ('enrolled', 'consulted');
END;

CREATE TRIGGER IF NOT EXISTS bug_backfill_new_specialist_enrollment
AFTER INSERT ON project_specialist_enrollments
WHEN NEW.status IN ('enrolled', 'consulted')
BEGIN
    INSERT OR IGNORE INTO bug_specialist_assessments(
        bug_id, specialist_class_id, specialist_class_version, applicability
    )
    SELECT b.id, NEW.specialist_class_id, NEW.specialist_class_version, 'pending'
    FROM bugs b
    WHERE b.intent_id=NEW.intent_id AND b.status IN ('registered', 'triaging', 'prioritized');
END;

CREATE TRIGGER IF NOT EXISTS bug_priority_guard
BEFORE UPDATE OF status, priority_rank ON bugs
WHEN NEW.status IN ('prioritized', 'actioned', 'deferred')
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM bug_specialist_assessments a
        WHERE a.bug_id=NEW.id AND a.applicability='pending'
    ) THEN RAISE(ABORT, 'bug priority requires every enrolled specialist disposition') END;
    SELECT CASE WHEN NEW.priority_rank IS NULL OR length(trim(COALESCE(NEW.priority_rationale, ''))) = 0
        THEN RAISE(ABORT, 'bug priority requires rank and rationale') END;
END;

CREATE TRIGGER IF NOT EXISTS bug_resolution_guard
BEFORE UPDATE OF status ON bugs
WHEN NEW.status='resolved'
BEGIN
    SELECT CASE WHEN NEW.action_task_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM tasks t WHERE t.id=NEW.action_task_id AND t.column_name='Done'
    ) THEN RAISE(ABORT, 'bug resolution requires its action task to be Done') END;
END;

CREATE TRIGGER IF NOT EXISTS decision_update_to_learning_event
AFTER UPDATE OF status ON decisions
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO learning_events(occurred_at, event_type, outcome, reason_summary, intent_id, task_id, decision_id, reviewer_id)
    VALUES(COALESCE(NEW.resolved_at, NEW.created_at), 'decision.resolved', NEW.status, NEW.question, NEW.intent_id, NEW.task_id, NEW.id, NEW.decided_by);
END;

-- Relational workflow invariants. Keep these in SQLite so alternate clients
-- cannot bypass the coordinator helper.

CREATE TRIGGER IF NOT EXISTS task_insert_guard
BEFORE INSERT ON tasks
BEGIN
    SELECT CASE WHEN NEW.id = '' OR NEW.id GLOB '*[^a-z0-9-]*'
        OR NEW.id GLOB '-*' THEN RAISE(ABORT, 'invalid task id') END;
    SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM columns WHERE name = NEW.column_name AND active = 1)
        THEN RAISE(ABORT, 'unknown or inactive task column') END;
    SELECT CASE WHEN NOT json_valid(NEW.raw_json)
        THEN RAISE(ABORT, 'task raw_json must be valid JSON') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM column_wip_limits w
        WHERE w.column_name = NEW.column_name
          AND (SELECT COUNT(*) FROM tasks WHERE column_name = NEW.column_name) >= w.limit_value
    ) THEN RAISE(ABORT, 'column WIP limit exceeded') END;
END;

CREATE TRIGGER IF NOT EXISTS task_transition_guard
BEFORE UPDATE OF column_name ON tasks
WHEN OLD.column_name <> NEW.column_name
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM column_transitions
        WHERE from_column = OLD.column_name AND to_column = NEW.column_name
    ) THEN RAISE(ABORT, 'task transition is not allowed') END;
    SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM columns WHERE name = NEW.column_name AND active = 1)
        THEN RAISE(ABORT, 'unknown or inactive task column') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM column_wip_limits w
        WHERE w.column_name = NEW.column_name
          AND (SELECT COUNT(*) FROM tasks WHERE column_name = NEW.column_name) >= w.limit_value
    ) THEN RAISE(ABORT, 'column WIP limit exceeded') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM task_dependencies d
        LEFT JOIN tasks dependency_task ON dependency_task.id = d.dependency
        LEFT JOIN backlog_ideas dependency_idea ON dependency_idea.id = d.dependency
        WHERE d.task_id = NEW.id
          AND ((dependency_task.id IS NOT NULL AND dependency_task.column_name <> 'Done')
            OR (dependency_idea.id IS NOT NULL AND COALESCE(dependency_idea.status, '') <> 'done'))
    ) THEN RAISE(ABORT, 'task has unresolved dependencies') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM runs r LEFT JOIN autonomy_envelopes a ON a.run_id = r.id
        WHERE r.task_id = NEW.id AND r.status = 'active' AND a.run_id IS NULL
    ) THEN RAISE(ABORT, 'active run lacks autonomy envelope') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM quality_signals q WHERE q.task_id=NEW.id AND q.status <> 'resolved'
          AND q.severity IN ('stop-affected-work', 'stop-value-stream')
    ) THEN RAISE(ABORT, 'task has an unresolved stop-quality signal') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM review_plans p JOIN gates g ON g.id = p.assurance_gate_id
        WHERE p.task_id = NEW.id AND p.status = 'frozen'
          AND (p.scope_hash <> (SELECT scope_hash FROM task_work_profiles WHERE task_id = NEW.id)
            OR g.recommendation <> 'pass')
    ) THEN RAISE(ABORT, 'task assurance review is incomplete or stale') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM review_plans p
        WHERE p.task_id = NEW.id AND p.status = 'frozen'
          AND NOT EXISTS (
              SELECT 1 FROM guidance_snapshots s
              WHERE s.review_plan_id = p.id AND s.status = 'frozen'
                AND s.scope_hash = p.scope_hash
          )
    ) THEN RAISE(ABORT, 'task lacks a matching frozen guidance snapshot') END;
    SELECT CASE WHEN NEW.column_name = 'Active' AND EXISTS (
        SELECT 1 FROM guidance_snapshots s
        JOIN guidance_snapshot_tenets t ON t.guidance_snapshot_id = s.id
        WHERE s.task_id = NEW.id AND s.status = 'frozen'
          AND t.disposition = 'required' AND t.resolution IN ('pending', 'blocked')
    ) THEN RAISE(ABORT, 'required guidance is not translated into production work') END;
    SELECT CASE WHEN NEW.column_name IN ('Active', 'Done') AND EXISTS (
        SELECT 1 FROM review_plans p WHERE p.task_id = NEW.id AND p.status = 'stale'
    ) THEN RAISE(ABORT, 'task review plan is stale') END;
    SELECT CASE WHEN NEW.column_name = 'Done' AND EXISTS (
        SELECT 1 FROM gates g
        WHERE g.task_id = NEW.id AND g.applicability = 'applicable' AND g.recommendation <> 'pass'
    ) THEN RAISE(ABORT, 'task has an unsatisfied applicable gate') END;
    SELECT CASE WHEN NEW.column_name = 'Done' AND EXISTS (
        SELECT 1 FROM assurance_obligations o JOIN guidance_snapshots s ON s.id = o.guidance_snapshot_id
        WHERE s.task_id = NEW.id AND o.status IN ('planned', 'blocked')
    ) THEN RAISE(ABORT, 'task has an unsatisfied assurance obligation') END;
    SELECT CASE WHEN NEW.column_name = 'Done' AND EXISTS (
        SELECT 1 FROM quality_signals q
        WHERE q.task_id = NEW.id AND q.status <> 'resolved'
          AND q.severity IN ('stop-affected-work', 'stop-value-stream')
    ) THEN RAISE(ABORT, 'task has an unresolved stop-quality signal') END;
    SELECT CASE WHEN NEW.column_name = 'Done' AND EXISTS (
        SELECT 1 FROM json_each(NEW.raw_json, '$.exit_criteria') criterion
        WHERE NOT EXISTS (
            SELECT 1 FROM evidence e
            WHERE e.task_id = NEW.id AND e.result = 'pass'
              AND (e.criterion_id = CAST(criterion.key + 1 AS TEXT)
                OR e.criterion_id = CAST(criterion.value AS TEXT))
        )
    ) THEN RAISE(ABORT, 'task exit criterion lacks passing evidence') END;
END;

CREATE TRIGGER IF NOT EXISTS quality_signal_stops_active_task
AFTER INSERT ON quality_signals
WHEN NEW.severity IN ('stop-affected-work', 'stop-value-stream')
  AND (SELECT column_name FROM tasks WHERE id=NEW.task_id) = 'Active'
BEGIN
    UPDATE tasks SET column_name='Blocked', updated_at=NEW.opened_at WHERE id=NEW.task_id;
END;

CREATE TRIGGER IF NOT EXISTS task_dependency_guard
BEFORE INSERT ON task_dependencies
WHEN NEW.task_id = NEW.dependency
BEGIN
    SELECT RAISE(ABORT, 'task cannot depend on itself');
END;

CREATE TRIGGER IF NOT EXISTS decision_insert_guard
BEFORE INSERT ON decisions
BEGIN
    SELECT CASE WHEN NEW.id = '' OR NEW.id GLOB '*[^a-z0-9-]*' OR NEW.id GLOB '-*'
        THEN RAISE(ABORT, 'invalid decision id') END;
    SELECT CASE WHEN NEW.intent_id IS NULL AND NEW.task_id IS NULL
        THEN RAISE(ABORT, 'decision requires an intent or task') END;
    SELECT CASE WHEN NOT json_valid(NEW.options_json) OR json_type(NEW.options_json) <> 'array'
        THEN RAISE(ABORT, 'decision options must be a JSON array') END;
    SELECT CASE WHEN NEW.default_option IS NOT NULL
        AND json_array_length(NEW.options_json) > 0
        AND NOT EXISTS (SELECT 1 FROM json_each(NEW.options_json) WHERE value = NEW.default_option)
        THEN RAISE(ABORT, 'decision default is not a declared option') END;
END;

CREATE TRIGGER IF NOT EXISTS decision_resolution_guard
BEFORE UPDATE OF status, answer ON decisions
WHEN NEW.status = 'resolved'
BEGIN
    SELECT CASE WHEN OLD.status <> 'open'
        THEN RAISE(ABORT, 'only an open decision may be resolved') END;
    SELECT CASE WHEN NEW.answer IS NULL OR trim(NEW.answer) = ''
        THEN RAISE(ABORT, 'resolved decision requires an answer') END;
    SELECT CASE WHEN json_array_length(NEW.options_json) > 0
        AND NOT EXISTS (SELECT 1 FROM json_each(NEW.options_json) WHERE value = NEW.answer)
        THEN RAISE(ABORT, 'decision answer is not a declared option') END;
END;

CREATE TRIGGER IF NOT EXISTS autonomy_envelope_insert_guard
BEFORE INSERT ON autonomy_envelopes
BEGIN
    SELECT CASE WHEN NOT json_valid(NEW.policy_json) OR json_type(NEW.policy_json) <> 'object'
        THEN RAISE(ABORT, 'autonomy envelope must be a JSON object') END;
    SELECT CASE WHEN COALESCE(
        json_extract(NEW.policy_json, '$.network_policy') IN ('deny', 'allowlist'), 0
    ) = 0
        THEN RAISE(ABORT, 'invalid autonomy network policy') END;
    SELECT CASE WHEN json_type(NEW.policy_json, '$.max_steps') IS NOT 'integer'
        OR json_extract(NEW.policy_json, '$.max_steps') < 1
        OR json_type(NEW.policy_json, '$.max_duration_seconds') IS NOT 'integer'
        OR json_extract(NEW.policy_json, '$.max_duration_seconds') < 1
        OR json_type(NEW.policy_json, '$.max_retries') IS NOT 'integer'
        OR json_extract(NEW.policy_json, '$.max_retries') < 0
        OR json_type(NEW.policy_json, '$.max_concurrency') IS NOT 'integer'
        OR json_extract(NEW.policy_json, '$.max_concurrency') < 1
        THEN RAISE(ABORT, 'invalid autonomy envelope budget') END;
    SELECT CASE WHEN json_type(NEW.policy_json, '$.mode') IS NULL
        OR json_type(NEW.policy_json, '$.allowed_tools') IS NULL
        OR json_type(NEW.policy_json, '$.allowed_paths') IS NULL
        OR json_type(NEW.policy_json, '$.approval_required') IS NULL
        OR json_type(NEW.policy_json, '$.stop_conditions') IS NULL
        THEN RAISE(ABORT, 'autonomy envelope is incomplete') END;
END;

CREATE TRIGGER IF NOT EXISTS autonomy_envelope_immutable
BEFORE UPDATE ON autonomy_envelopes
BEGIN
    SELECT RAISE(ABORT, 'autonomy envelope is immutable');
END;

CREATE TRIGGER IF NOT EXISTS gate_result_guard
BEFORE UPDATE OF recommendation, execution_status, independent ON gates
BEGIN
    SELECT CASE WHEN NEW.recommendation = 'not-applicable'
        AND NEW.applicability <> 'not-applicable'
        THEN RAISE(ABORT, 'only a not-applicable gate may return not-applicable') END;
    SELECT CASE WHEN NEW.gate_type = 'independent-review'
        AND NEW.recommendation = 'pass' AND NEW.independent <> 1
        THEN RAISE(ABORT, 'independent review requires an independent evaluator') END;
    SELECT CASE WHEN NEW.recommendation = 'pass' AND EXISTS (
        SELECT 1 FROM gate_specialist_requirements r
        WHERE r.gate_id = NEW.id AND r.status = 'pending'
    ) THEN RAISE(ABORT, 'gate has pending specialist requirements') END;
    SELECT CASE WHEN NEW.recommendation = 'pass' AND EXISTS (
        SELECT 1 FROM review_plan_items i
        WHERE i.gate_id = NEW.id AND i.status IN ('pending', 'blocked')
    ) THEN RAISE(ABORT, 'gate has unresolved review plan items') END;
END;

CREATE TRIGGER IF NOT EXISTS gate_insert_guard
BEFORE INSERT ON gates
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM gate_types t WHERE t.id = NEW.gate_type AND t.active = 1
    ) THEN RAISE(ABORT, 'unknown or inactive gate type') END;
END;

CREATE TRIGGER IF NOT EXISTS specialist_requirement_insert_guard
BEFORE INSERT ON gate_specialist_requirements
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM gates g WHERE g.id = NEW.gate_id AND g.applicability <> 'not-applicable'
    ) THEN RAISE(ABORT, 'specialist requirement needs an applicable or undetermined gate') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM gates g
        WHERE g.id = NEW.gate_id AND g.gate_type = 'independent-review'
          AND NEW.engagement_role <> 'review'
    ) THEN RAISE(ABORT, 'independent-review gate requires a review specialist') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM specialist_classes c
        WHERE c.id = NEW.specialist_class_id AND c.active = 1
          AND c.version = NEW.specialist_class_version
    ) THEN RAISE(ABORT, 'specialist class is inactive or version is not current') END;
END;

CREATE TRIGGER IF NOT EXISTS specialist_handoff_insert_guard
BEFORE INSERT ON specialist_handoffs
BEGIN
    SELECT CASE WHEN NEW.engagement_role = 'review' AND NEW.independent <> 1
        THEN RAISE(ABORT, 'review handoff must be independent') END;
    SELECT CASE WHEN NEW.gate_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM gate_specialist_requirements r
        WHERE r.gate_id = NEW.gate_id
          AND r.specialist_class_id = NEW.specialist_class_id
          AND r.specialist_class_version = NEW.specialist_class_version
          AND r.engagement_role = NEW.engagement_role
    ) THEN RAISE(ABORT, 'handoff has no matching specialist requirement') END;
    SELECT CASE WHEN NEW.gate_id IS NOT NULL AND NEW.task_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM gates g WHERE g.id = NEW.gate_id AND g.task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'handoff gate belongs to another task') END;
    SELECT CASE WHEN NEW.review_plan_item_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM review_plan_items i JOIN review_plans p ON p.id = i.review_plan_id
        WHERE i.id = NEW.review_plan_item_id
          AND i.gate_id = NEW.gate_id
          AND p.task_id = NEW.task_id
          AND i.specialist_class_id = NEW.specialist_class_id
          AND i.specialist_class_version = NEW.specialist_class_version
          AND i.engagement_role = NEW.engagement_role
          AND i.purpose = NEW.review_purpose
          AND i.status = 'pending'
    ) THEN RAISE(ABORT, 'handoff does not match a pending review plan item') END;
END;

CREATE TRIGGER IF NOT EXISTS review_plan_freeze_guard
BEFORE UPDATE OF status ON review_plans
WHEN NEW.status = 'frozen' AND OLD.status = 'draft'
BEGIN
    SELECT CASE WHEN NEW.scope_hash <> (
        SELECT scope_hash FROM task_work_profiles WHERE task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'review plan scope is stale') END;
    SELECT CASE WHEN (
        SELECT COUNT(*) FROM review_plan_items WHERE review_plan_id = NEW.id
    ) <> 2 * (
        SELECT COUNT(*) FROM specialist_classes WHERE active = 1
    ) THEN RAISE(ABORT, 'review plan does not cover every active specialist class and purpose') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM specialist_classes c
        WHERE c.active = 1 AND (
            NOT EXISTS (SELECT 1 FROM review_plan_items i WHERE i.review_plan_id = NEW.id AND i.specialist_class_id = c.id AND i.purpose = 'assurance')
            OR NOT EXISTS (SELECT 1 FROM review_plan_items i WHERE i.review_plan_id = NEW.id AND i.specialist_class_id = c.id AND i.purpose = 'control')
        )
    ) THEN RAISE(ABORT, 'review plan is missing an active specialist class or purpose') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM review_plan_items i JOIN specialist_classes c ON c.id = i.specialist_class_id
        WHERE i.review_plan_id = NEW.id AND c.active = 0
    ) THEN RAISE(ABORT, 'review plan includes an inactive specialist class') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM gates a JOIN gates c ON c.id = NEW.control_gate_id
        WHERE a.id = NEW.assurance_gate_id AND a.task_id = NEW.task_id AND c.task_id = NEW.task_id
          AND a.gate_type = 'assurance-readiness' AND c.gate_type = 'independent-review'
    ) THEN RAISE(ABORT, 'review plan gates do not match task and purpose') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM guidance_snapshots s
        WHERE s.review_plan_id = NEW.id AND s.task_id = NEW.task_id
          AND s.scope_hash = NEW.scope_hash AND s.status = 'frozen'
    ) THEN RAISE(ABORT, 'review plan requires a matching frozen guidance snapshot') END;
END;

CREATE TRIGGER IF NOT EXISTS guidance_snapshot_freeze_guard
BEFORE UPDATE OF status ON guidance_snapshots
WHEN NEW.status = 'frozen' AND OLD.status = 'draft'
BEGIN
    SELECT CASE WHEN NEW.scope_hash <> (
        SELECT scope_hash FROM task_work_profiles WHERE task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'guidance snapshot scope is stale') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM review_plans p WHERE p.id = NEW.review_plan_id
          AND p.task_id = NEW.task_id AND p.status = 'draft'
    ) THEN RAISE(ABORT, 'guidance snapshot must freeze with its draft review plan') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM tenets t JOIN tenet_versions v
          ON v.tenet_id = t.id AND v.version = t.current_version
        WHERE t.active = 1 AND v.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM guidance_snapshot_tenets s
              WHERE s.guidance_snapshot_id = NEW.id AND s.tenet_id = t.id
                AND s.tenet_version = t.current_version
          )
          AND NOT EXISTS (
              SELECT 1 FROM experiment_assignments a
              JOIN improvement_experiments e ON e.id=a.experiment_id
              JOIN guidance_snapshot_tenets s ON s.guidance_snapshot_id=NEW.id
                AND s.tenet_id=e.variant_tenet_id AND s.tenet_version=e.variant_tenet_version
              WHERE a.task_id=NEW.task_id AND a.arm='variant' AND e.status='running'
                AND e.baseline_tenet_id=t.id
          )
    ) THEN RAISE(ABORT, 'guidance snapshot omits an active tenet') END;
END;

CREATE TRIGGER IF NOT EXISTS guidance_snapshot_identity_immutable
BEFORE UPDATE OF task_id, review_plan_id, scope_hash, guidance_hash ON guidance_snapshots
WHEN OLD.status <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'frozen guidance snapshot identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS guidance_snapshot_tenet_identity_immutable
BEFORE UPDATE OF guidance_snapshot_id, tenet_id, tenet_version, disposition ON guidance_snapshot_tenets
WHEN (SELECT status FROM guidance_snapshots WHERE id = OLD.guidance_snapshot_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'frozen guidance tenet identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS guidance_resolution_guard
BEFORE UPDATE OF resolution ON guidance_snapshot_tenets
WHEN NEW.resolution = 'materialized'
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM assurance_obligations o
        WHERE o.guidance_snapshot_id = NEW.guidance_snapshot_id AND o.tenet_id = NEW.tenet_id
    ) THEN RAISE(ABORT, 'materialized guidance requires a production obligation') END;
END;

CREATE TRIGGER IF NOT EXISTS assurance_obligation_integrity_guard
BEFORE INSERT ON assurance_obligations
BEGIN
    SELECT CASE WHEN NEW.review_plan_item_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM review_plan_items i JOIN review_plans p ON p.id = i.review_plan_id
        JOIN guidance_snapshots s ON s.review_plan_id = p.id
        WHERE i.id = NEW.review_plan_item_id AND s.id = NEW.guidance_snapshot_id
          AND i.purpose = 'assurance'
    ) THEN RAISE(ABORT, 'obligation must originate from assurance in the same plan') END;
END;

CREATE TRIGGER IF NOT EXISTS tenet_version_immutable_after_snapshot
BEFORE UPDATE OF instruction, intended_effect, strength, exception_authority,
    verification_strategy, experiment_eligible, effective_at, created_at
ON tenet_versions
WHEN EXISTS (
    SELECT 1 FROM guidance_snapshot_tenets s
    WHERE s.tenet_id = OLD.tenet_id AND s.tenet_version = OLD.version
)
BEGIN
    SELECT RAISE(ABORT, 'a tenet version used by a guidance snapshot is immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_plan_rule_binding_guard
BEFORE INSERT ON review_plan_rule_bindings
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM review_plans p
        WHERE p.id = NEW.review_plan_id AND p.policy_id = NEW.policy_id
          AND p.policy_version = NEW.policy_version AND p.status = 'draft'
    ) THEN RAISE(ABORT, 'review rule binding does not match the draft plan policy') END;
END;

CREATE TRIGGER IF NOT EXISTS review_plan_identity_immutable
BEFORE UPDATE OF task_id, policy_id, policy_version, scope_hash, assurance_gate_id, control_gate_id
ON review_plans
WHEN OLD.status <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'frozen review plan identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_plan_complete_guard
BEFORE UPDATE OF status ON review_plans
WHEN NEW.status = 'complete'
BEGIN
    SELECT CASE WHEN OLD.status <> 'frozen'
        OR EXISTS (SELECT 1 FROM review_plan_items i WHERE i.review_plan_id = NEW.id AND i.status IN ('pending', 'blocked'))
        OR (SELECT recommendation FROM gates WHERE id = NEW.assurance_gate_id) <> 'pass'
        OR (SELECT recommendation FROM gates WHERE id = NEW.control_gate_id) <> 'pass'
        THEN RAISE(ABORT, 'review plan cannot complete before both gates and all items pass') END;
END;

CREATE TRIGGER IF NOT EXISTS review_plan_item_identity_immutable
BEFORE UPDATE OF review_plan_id, gate_id, specialist_class_id, specialist_class_version,
    purpose, engagement_role, policy_disposition, policy_rule_id
ON review_plan_items
WHEN (SELECT status FROM review_plans WHERE id = OLD.review_plan_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'frozen review plan item identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_plan_item_delete_guard
BEFORE DELETE ON review_plan_items
WHEN (SELECT status FROM review_plans WHERE id = OLD.review_plan_id) <> 'draft'
BEGIN
    SELECT RAISE(ABORT, 'frozen review plan items cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS review_plan_item_resolution_guard
BEFORE UPDATE OF status, satisfied_by_handoff_id ON review_plan_items
WHEN NEW.status IN ('satisfied', 'not-applicable') AND NEW.applicability_source <> 'policy'
BEGIN
    SELECT CASE WHEN NEW.satisfied_by_handoff_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM specialist_handoffs h
        WHERE h.id = NEW.satisfied_by_handoff_id
          AND h.review_plan_item_id = NEW.id
          AND h.review_purpose = NEW.purpose
    ) THEN RAISE(ABORT, 'review plan item resolution requires its matching handoff') END;
END;

CREATE TRIGGER IF NOT EXISTS review_plan_policy_exception_guard
BEFORE UPDATE OF status, applicability, applicability_source ON review_plan_items
WHEN NEW.status = 'not-applicable' AND NEW.applicability_source = 'policy'
BEGIN
    SELECT CASE WHEN NEW.policy_rule_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM review_plan_rule_bindings b
        JOIN review_policy_rules r ON r.policy_id = b.policy_id
          AND r.policy_version = b.policy_version AND r.id = b.rule_id
        WHERE b.review_plan_id = NEW.review_plan_id AND b.rule_id = NEW.policy_rule_id
          AND r.disposition IN ('normally-not-applicable', 'conditional')
    ) THEN RAISE(ABORT, 'policy not-applicable requires a matching exception rule') END;
END;

CREATE TRIGGER IF NOT EXISTS review_plan_policy_exception_insert_guard
BEFORE INSERT ON review_plan_items
WHEN NEW.status = 'not-applicable' AND NEW.applicability_source = 'policy'
BEGIN
    SELECT CASE WHEN NEW.policy_rule_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM review_plan_rule_bindings b
        JOIN review_policy_rules r ON r.policy_id = b.policy_id
          AND r.policy_version = b.policy_version AND r.id = b.rule_id
        WHERE b.review_plan_id = NEW.review_plan_id AND b.rule_id = NEW.policy_rule_id
          AND r.disposition IN ('normally-not-applicable', 'conditional')
    ) THEN RAISE(ABORT, 'policy not-applicable requires a matching exception rule') END;
END;

CREATE TRIGGER IF NOT EXISTS review_policy_immutable_after_use
BEFORE UPDATE ON review_policies
WHEN EXISTS (
    SELECT 1 FROM review_plans p WHERE p.policy_id = OLD.id AND p.policy_version = OLD.version
)
BEGIN
    SELECT RAISE(ABORT, 'a policy version used by a review plan is immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_policy_rule_immutable_after_use
BEFORE UPDATE ON review_policy_rules
WHEN EXISTS (
    SELECT 1 FROM review_plan_rule_bindings b
    WHERE b.policy_id = OLD.policy_id AND b.policy_version = OLD.policy_version AND b.rule_id = OLD.id
)
BEGIN
    SELECT RAISE(ABORT, 'a policy rule used by a review plan is immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_profile_stales_plan
AFTER UPDATE OF scope_hash ON task_work_profiles
WHEN OLD.scope_hash <> NEW.scope_hash
BEGIN
    UPDATE review_plans SET status = 'stale'
    WHERE task_id = NEW.task_id AND status IN ('draft', 'frozen', 'complete');
    UPDATE guidance_snapshots SET status = 'stale'
    WHERE task_id = NEW.task_id AND status IN ('draft', 'frozen', 'complete');
END;

CREATE TRIGGER IF NOT EXISTS evidence_insert_guard
BEFORE INSERT ON evidence
BEGIN
    SELECT CASE WHEN trim(NEW.revision) = '' THEN RAISE(ABORT, 'evidence requires a revision') END;
    SELECT CASE WHEN NEW.gate_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM gates g WHERE g.id = NEW.gate_id AND g.task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'evidence gate belongs to another task') END;
END;

CREATE TRIGGER IF NOT EXISTS evidence_update_guard
BEFORE UPDATE OF task_id, gate_id, revision ON evidence
BEGIN
    SELECT CASE WHEN trim(NEW.revision) = '' THEN RAISE(ABORT, 'evidence requires a revision') END;
    SELECT CASE WHEN NEW.gate_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM gates g WHERE g.id = NEW.gate_id AND g.task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'evidence gate belongs to another task') END;
END;

CREATE TRIGGER IF NOT EXISTS intent_realization_guard
BEFORE UPDATE OF state, closure ON intents
WHEN NEW.state = 'closed' AND NEW.closure = 'realized'
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM intent_work_links l JOIN tasks t ON t.id = l.task_id
        WHERE l.intent_id = NEW.id AND t.column_name <> 'Done'
    ) THEN RAISE(ABORT, 'realized intent has unfinished work') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM decisions d WHERE d.intent_id = NEW.id AND d.status = 'open'
    ) THEN RAISE(ABORT, 'realized intent has an open decision') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM bugs b WHERE b.intent_id=NEW.id AND b.status NOT IN ('resolved', 'rejected')
    ) THEN RAISE(ABORT, 'realized intent has an unresolved bug') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM specialist_guidance_proposals p WHERE p.intent_id=NEW.id AND p.status='proposed'
    ) THEN RAISE(ABORT, 'realized intent has an unresolved specialist guidance proposal') END;
END;

CREATE TRIGGER IF NOT EXISTS intent_insert_guard
BEFORE INSERT ON intents
BEGIN
    SELECT CASE WHEN NEW.id = '' OR NEW.id GLOB '*[^a-z0-9-]*' OR NEW.id GLOB '-*'
        THEN RAISE(ABORT, 'invalid intent id') END;
    SELECT CASE WHEN trim(NEW.summary) = '' THEN RAISE(ABORT, 'intent summary is required') END;
    SELECT CASE WHEN NOT json_valid(NEW.raw_json)
        THEN RAISE(ABORT, 'intent raw_json must be valid JSON') END;
END;
