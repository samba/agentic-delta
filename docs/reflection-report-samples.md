# Reflection Report Samples

This file contains template-aligned example outputs for a reflection loop in a simulated Python web service with a graph-database backend.

## Sample A: Short Reflection (Last 48 Hours)

## Timeframe

- Window: 2026-04-01 00:00 UTC to 2026-04-03 00:00 UTC
- Evidence cutoff: 2026-04-03 00:00 UTC
- Assumptions: Includes merged API/query-layer changes and deployment adjustments in this window.

## Context Partitioning

- `project-context`: repository/process-specific findings and actions.
- `abstract-method`: reusable workflow/reasoning improvements.
- Classification gate:
  - Topic: Recommendation query duplicates
  - `track=project-context`, `evidence_scope=project-only`, `split_handling=single-track`, `applicability_realm=project-only`, `applicability_signal=none`
  - Reason summary: The issue is tied to this service's current graph data shape and endpoint behavior.
- Classification gate:
  - Topic: Pre-coding data-handling start gate
  - `track=abstract-method`, `evidence_scope=cross-project`, `split_handling=paired`, `applicability_realm=discipline-general`, `applicability_signal=field-research`
  - Reason summary: The sequence (schema review -> query-plan review -> preflight drift check) is portable across graph-backed service teams.
- Leakage check: abstract-method outputs avoid project-specific identifiers.

## A Priori Knowledge Audit

- Known facts before execution: recommendation fan-out behavior was sensitive to query-shape changes; prior soak tests had already shown occasional async session lifecycle instability.
- Assumptions made: index updates and aggregation adjustments would not affect downstream relationship envelope expectations.
- Assumptions acted on without verification: optimization branch changes were implemented before completing query-stream preflight checks against downstream expectations.
- Audit implication: add explicit pre-coding verification gates and block implementation start when baseline checks are incomplete.

## High-Signal Outcomes

### project-context

1. Outcome: Reduced P95 latency on relationship-traversal endpoints.
   - Value delivered: Faster user-facing graph exploration.
   - Evidence: P95 dropped from 420ms to 260ms after query/index changes.
   - Why it worked: Plan-driven index updates targeted the highest-cost traversals.

2. Outcome: Stabilized graph-driver session lifecycle.
   - Value delivered: Fewer runtime interruptions in sustained traffic windows.
   - Evidence: Open-session count stayed flat in soak testing.
   - Why it worked: Session scope moved to explicit context-managed boundaries.

### abstract-method

1. Outcome: Pre-coding discovery gate reduced downstream rework.
   - Value delivered: Lower schema/query drift and fewer late-stage correctness regressions.
   - Evidence: Work items that completed schema review, query-plan review, and preflight drift checks before coding had fewer rework loops.
   - Why it worked: Drift was caught before implementation rather than after integration.

2. Outcome: Planning artifacts became actionable for code generation.
   - Value delivered: Less ambiguity in implementation tasks.
   - Evidence: Fewer corrective edits in first-pass merge requests.
   - Why it worked: The implementation plan encoded concrete query-stream expectations.

## Negative Signals and Friction

### project-context

1. Pattern: Duplicate nodes in recommendations under high fan-out.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: uniqueness/cardinality assertions were feasible and should have been required before merge.
   - Failure mode: Aggregation path produced repeated nodes.
   - Evidence: `test_recommendations_unique_nodes` failed.
   - Impact: Incorrect recommendations and avoidable client-side deduping.
   - Preventive rule: Require uniqueness assertions and cardinality checks in integration tests for fan-out queries.

2. Pattern: Intermittent connection leaks in async graph-driver sessions.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: existing soak-test evidence already indicated session-scope risk and should have blocked rollout without error-path coverage.
   - Failure mode: Session lifecycle escaped request scope under error paths.
   - Evidence: Soak tests showed steadily rising open sessions.
   - Impact: Elevated resource pressure and unstable tail latencies.
   - Preventive rule: Enforce context-managed session boundaries in repository adapters and verify with soak tests.

### abstract-method

1. Pattern: Data-handling work started without schema compatibility review.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: schema/query preflight gates were available and would have caught the mismatch before coding.
   - Failure mode: Edge filters were introduced without validating required relationship availability.
   - Evidence: Query-stream preflight flagged unexpected null traversals.
   - Impact: Avoidable rework to revert and re-plan implementation.
   - Preventive rule: Do not begin code generation until schema review, query-plan review, and preflight drift checks are complete.

2. Pattern: Query optimization landed without stream-expectation baseline.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: baseline generation was part of planning and should have been mandatory for query-shape changes.
   - Failure mode: Ranking pipeline received missing edges after optimization.
   - Evidence: Relationship-count mismatch alert in downstream service.
   - Impact: Rework in ranking logic and rollback overhead.
   - Preventive rule: Require expectation baselines in planning and CI before query-shape changes merge.

## Metrics and Criteria That Mattered

### project-context

- Most useful indicators: API P95/P99 latency, query cardinality, connection pool stability.
- Weak indicators: raw commit count.
- Thresholds/gates to keep: block release when P95 regresses more than 15% on graph-heavy endpoints.
- Thresholds/gates to revise: tighten soak-test duration for session leak detection.

### abstract-method

- Most useful indicators: preflight drift detections, query-plan regression count, schema compatibility failures.
- Weak indicators: total documentation volume.
- Thresholds/gates to keep: require schema review + query-plan review + preflight drift check during planning before code generation.
- Thresholds/gates to revise: add stricter acceptance limits for relationship-count variance.

## Reinforcement Actions (Prioritized)

### project-context

1. Action: Add query plan snapshots for top 5 high-cost endpoints.
   - Owner: backend maintainer
   - Scope: recommendation and traversal endpoints
   - Completion signal: stored plans + release-over-release cost deltas

2. Action: Extend soak tests to cover error-path session handling.
   - Owner: platform engineer
   - Scope: async graph-driver adapter layer
   - Completion signal: stable open-session curve across 45-minute runs

### abstract-method

1. Action: Standardize pre-coding discovery gate for graph-data tasks.
   - Owner: backend lead
   - Scope: all graph-query feature work
   - Completion signal: each task includes schema review, query-plan review, and preflight drift record in implementation plan

2. Action: Enforce preflight baseline checks in CI for query-shape changes.
   - Owner: release engineer
   - Scope: graph query pipeline
   - Completion signal: CI fails when expected-vs-observed relationship envelopes drift beyond threshold

## Precursor Research and Applicability Mapping

1. Candidate refinement:
   - Track (`project-context` | `abstract-method`): `abstract-method`
   - Precursor research summary:
     - Search keywords for future research: "graph schema review checklist", "Cypher query plan regression", "query stream drift preflight"
     - Early research findings: graph-backed API teams reduce regressions when read/research and plan refinement enforce the three-step pre-coding gate.
     - Proof material links: internal query-plan snapshots, preflight drift reports, latency/correctness dashboards.
   - Applicability realm (`project-only` | `project-family` | `discipline-general`): `discipline-general`
   - Signal source (`user-assertion` | `field-research` | `both`): `field-research`
   - Promotion recommendation (`keep project-context` | `promote abstract-method` | `defer`): `promote abstract-method`

2. Candidate refinement:
   - Track (`project-context` | `abstract-method`): `project-context`
   - Precursor research summary:
     - Search keywords for future research: "recommendation query cardinality", "async graph driver pooling"
     - Early research findings: current schema/index naming patterns are specific to this service's graph model.
     - Proof material links: query plans, endpoint traces, migration diffs.
   - Applicability realm (`project-only` | `project-family` | `discipline-general`): `project-only`
   - Signal source (`user-assertion` | `field-research` | `both`): `none`
   - Promotion recommendation (`keep project-context` | `promote abstract-method` | `defer`): `keep project-context`

## Skill Deltas (Two-Fold)

- Reason summary: project-context deltas capture service-specific query/index behavior; abstract-method deltas capture portable pre-coding discovery discipline.
- For each abstract-method delta, include evidence quality, stability, applicability signal(s), overlap, portability, boundary definition, applicability realm, and rollback/deprecation condition.
- For each new skill, include the split/merge rationale and the user confirmation point.

### project-context deltas

- Updated project procedures/docs: graph-query performance checklist and migration assertion checklist.
- New project-specific process artifacts: relationship cardinality baseline sheet for recommendation endpoints.
- Supporting references created/updated: query tuning runbook and endpoint latency notes.

### abstract-method deltas

- Updated reusable skills: add pre-coding discovery gate for data-handling work (schema review -> query-plan review -> preflight drift check).
- New reusable skills: none in this cycle.
- Supporting references created/updated: preflight drift checklist and plan-review rubric.
- Promotion summary reference: Candidate refinement #1 in precursor mapping.
- Evidence quality: pass (multiple incidents + benchmark evidence).
- Stability: pass (held across two release cycles).
- Applicability signal(s): field-research.
- Overlap: pass (no equivalent existing rule in current workflow).
- Portability: pass (applies across graph-backed service teams after removing project-specific names).
- Boundary definition: applies to data-handling/query-shape changes, not generic UI-only changes.
- Applicability realm: discipline-general.
- Rollback/deprecation condition: deprecate if gate causes measurable delivery delays without reducing rework for two consecutive cycles.

## Backlog and Hypotheses (Two-Track)

### project-context

1. Topic: Add property-based tests for recommendation graph invariants.
   - Why now: duplicates/leaks surfaced under broad graph expansion.
   - Expected impact: earlier detection of cardinality and uniqueness regressions.
   - Next experiment: random graph fixtures with uniqueness + bounded traversal assertions.

2. Topic: Improve migration rollback observability.
   - Why now: rollback confidence remains partial for multi-step schema changes.
   - Expected impact: faster and safer rollback decisions.
   - Next experiment: capture rollback timing and data-integrity checks per migration stage.

### abstract-method

1. Topic: Automate preflight drift validation in CI.
   - Why now: manual preflight is effective but inconsistently enforced.
   - Expected impact: lower regression escape rate on query-shape changes.
   - Next experiment: expected-vs-observed relationship envelope checks as required CI gate.

2. Topic: Standardize query-plan review checklist for graph-backed APIs.
   - Why now: plan regressions remain a recurring failure mode.
   - Expected impact: fewer high-cost plan regressions reaching load testing.
   - Next experiment: require checklist completion in pull requests that modify graph queries.

---

## Sample B: Full Reflection (Last 7 Days)

## Timeframe

- Window: 2026-03-27 00:00 UTC to 2026-04-03 00:00 UTC
- Evidence cutoff: 2026-04-03 00:00 UTC
- Assumptions: Includes API changes, graph schema/index updates, migration scripts, and deployment adjustments.

## Context Partitioning

- `project-context`: service-specific findings tied to current schema, migrations, and endpoint behavior.
- `abstract-method`: reusable engineering discipline for graph-backed backend changes.
- Classification gate:
  - Topic: Migration index naming mismatch
  - `track=project-context`, `evidence_scope=project-only`, `split_handling=single-track`, `applicability_realm=project-only`, `applicability_signal=none`
  - Reason summary: Bound to this project's schema naming and migration chain.
- Classification gate:
  - Topic: Pre-coding discovery gate
  - `track=abstract-method`, `evidence_scope=cross-project`, `split_handling=paired`, `applicability_realm=discipline-general`, `applicability_signal=both`
  - Reason summary: Portable engineering discipline with both observed project value and field support.
- Leakage check: abstract-method outputs exclude project-specific paths and naming.

## A Priori Knowledge Audit

- Known facts before execution: migration/index drift had previously impacted plan quality, and retry behavior on non-idempotent writes was known to be high-risk.
- Assumptions made: migration naming updates and retry middleware changes would remain behaviorally safe without expanded replay validation.
- Assumptions acted on without verification: query optimization and migration-related adjustments were advanced before complete expectation-baseline confirmation.
- Audit implication: enforce earlier baseline evidence capture and tighten rollout gates for migration and retry-path changes.

## High-Signal Outcomes

### project-context

1. Outcome: Recommendation endpoint P99 recovered after targeted query-shape corrections.
   - Value delivered: Stable user-facing response times under peak graph expansion.
   - Evidence: P99 returned from 1.4s to 810ms.
   - Why it worked: Depth cap and selective edge filtering reduced worst-case expansion.

2. Outcome: Migration checks prevented repeated index drift.
   - Value delivered: Faster post-migration stabilization.
   - Evidence: Query plans consistently used index seeks after correction.
   - Why it worked: Migration assertions validated index-property alignment immediately.

### abstract-method

1. Outcome: Planning-first discovery reduced late-cycle defects.
   - Value delivered: Lower rework in implementation and integration phases.
   - Evidence: Fewer code reversions on branches that completed discovery gate before coding.
   - Why it worked: Risks were surfaced in planning artifacts and preflight checks.

2. Outcome: Query-stream expectation baselines improved downstream safety.
   - Value delivered: Reduced ranking-service mismatches after query changes.
   - Evidence: Relationship-count variance stayed within envelope after baseline enforcement.
   - Why it worked: Query changes were validated against expected stream behavior pre-merge.

## Negative Signals and Friction

### project-context

1. Pattern: Migration created index with mismatched property casing.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: migration assertions could validate property naming deterministically before deployment.
   - Failure mode: Label scan fallback after migration.
   - Evidence: Query plan regression immediately post-migration.
   - Impact: Latency regression risk and recovery overhead.
   - Preventive rule: enforce migration assertions on index property names before deploy.

2. Pattern: Retry middleware amplified transient driver failures into duplicate writes.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: idempotency-key and retry-policy controls were known mitigations and should have been required.
   - Failure mode: retried non-idempotent write path.
   - Evidence: duplicate recommendation edges found in replay tests.
   - Impact: data correctness risk and cleanup rework.
   - Preventive rule: narrow retryable exception set and require idempotency keys.

### abstract-method

1. Pattern: Query optimization merged without preflight expectation baseline.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: expectation-baseline checks were already identified as required for this class of change.
   - Failure mode: missing edges in downstream ranking stream.
   - Evidence: expected-vs-observed relationship mismatch alerts.
   - Impact: ranking quality regression and emergency rollback.
   - Preventive rule: preflight expectation baseline must pass before merge for query-shape changes.

2. Pattern: Query-plan review skipped during early implementation.
   - Miss classification (`preventable` | `non-preventable`): `preventable`
   - Miss rationale: plan review could be completed pre-coding with low incremental cost and high risk reduction.
   - Failure mode: high-cost plan reached load testing.
   - Evidence: avoidable P99 spike on graph-heavy endpoint.
   - Impact: delayed release and additional tuning cycle.
   - Preventive rule: require query-plan review record in implementation plan before coding.

## Metrics and Criteria That Mattered

### project-context

- Most useful indicators: API P95/P99 latency, graph query cardinality, connection pool stability.
- Weak indicators: raw commit count.
- Thresholds/gates to keep: release block when P95 regression exceeds 15% on graph-heavy endpoints.
- Thresholds/gates to revise: tighten alerting thresholds for relationship-count variance.

### abstract-method

- Most useful indicators: preflight drift detections, query-plan regression count, schema compatibility failures.
- Weak indicators: total documentation volume.
- Thresholds/gates to keep: require schema review + query-plan review + preflight drift check during planning before code generation.
- Thresholds/gates to revise: add stricter enforcement for missing planning artifacts in pull requests.

## Reinforcement Actions (Prioritized)

### project-context

1. Action: Add migration dry-run and rollback simulation to release checklist.
   - Owner: release engineer
   - Scope: graph schema/index migration pipeline
   - Completion signal: each migration includes verified rollback path and integrity checks

2. Action: Expand load tests for deep relationship expansion scenarios.
   - Owner: performance engineer
   - Scope: recommendation and ranking endpoints
   - Completion signal: load suite covers depth-expanded paths with stable latency envelopes

### abstract-method

1. Action: Enforce planning artifacts for all graph query changes.
   - Owner: backend lead
   - Scope: graph-query pull requests
   - Completion signal: PRs require schema review, query-plan review, and preflight drift record prior to code approval

2. Action: Integrate CI checks for query-stream expectation coverage.
   - Owner: platform engineer
   - Scope: graph query pipelines
   - Completion signal: CI fails when expectation baselines are missing or out of envelope

## Precursor Research and Applicability Mapping

1. Candidate refinement:
   - Track (`project-context` | `abstract-method`): `abstract-method`
   - Precursor research summary:
     - Search keywords for future research: "graph schema review checklist", "Cypher query plan regression", "query stream drift preflight"
     - Early research findings: graph-backed API teams reduce regressions when planning and research enforce discovery gates before code generation.
     - Proof material links: query-plan snapshots, preflight drift reports, latency/correctness dashboards.
   - Applicability realm (`project-only` | `project-family` | `discipline-general`): `discipline-general`
   - Signal source (`user-assertion` | `field-research` | `both`): `both`
   - Promotion recommendation (`keep project-context` | `promote abstract-method` | `defer`): `promote abstract-method`

2. Candidate refinement:
   - Track (`project-context` | `abstract-method`): `project-context`
   - Precursor research summary:
     - Search keywords for future research: "Cypher index strategy", "Python async graph driver pooling"
     - Early research findings: schema/index naming and migration order are specific to current service topology.
     - Proof material links: migration diffs, endpoint traces, query plans.
   - Applicability realm (`project-only` | `project-family` | `discipline-general`): `project-only`
   - Signal source (`user-assertion` | `field-research` | `both`): `field-research`
   - Promotion recommendation (`keep project-context` | `promote abstract-method` | `defer`): `keep project-context`

## Skill Deltas (Two-Fold)

- Reason summary: project-context deltas capture service-specific migration/query behavior; abstract-method deltas capture reusable pre-coding discovery discipline for graph-backed backends.
- For each abstract-method delta, include evidence quality, stability, applicability signal(s), overlap, portability, boundary definition, applicability realm, and rollback/deprecation condition.
- For each new skill, include the split/merge rationale and the user confirmation point.

### project-context deltas

- Updated project procedures/docs: migration assertion checklist, query-stream baseline checklist, rollback simulation checklist.
- New project-specific process artifacts: endpoint-specific relationship envelope baselines.
- Supporting references created/updated: query tuning runbook and release readiness notes.

### abstract-method deltas

- Updated reusable skills: enforce planning-first discovery gate for data-handling changes.
- New reusable skills: none in this cycle.
- Supporting references created/updated: planning rubric for schema/query/preflight checks.
- Promotion summary reference: Candidate refinement #1 in precursor mapping.
- Evidence quality: pass (multiple incidents + benchmark + replay evidence).
- Stability: pass (maintained over weekly cycle).
- Applicability signal(s): both.
- Overlap: pass (no equivalent existing rule in baseline process).
- Portability: pass (works after removing service-specific names).
- Boundary definition: applies to backend data-handling/query changes, not generic non-data UI changes.
- Applicability realm: discipline-general.
- Rollback/deprecation condition: deprecate if enforced gate increases delivery time without measurable reduction in rework for two consecutive cycles.

## Backlog and Hypotheses (Two-Track)

### project-context

1. Topic: Improve migration rollback confidence for multi-step schema changes.
   - Why now: partially mitigated risk remains.
   - Expected impact: faster and safer rollback decisions.
   - Next experiment: staged rollback drills with integrity checks.

2. Topic: Broaden replay coverage for retry/idempotency paths.
   - Why now: duplicate-write risk surfaced during transient failures.
   - Expected impact: lower correctness regressions under retry conditions.
   - Next experiment: replay matrix with fault injection for graph-driver exceptions.

### abstract-method

1. Topic: Add CI gate for missing planning artifacts on graph-query changes.
   - Why now: skipping planning artifacts remains a repeated precursor to regressions.
   - Expected impact: lower query-regression escape rate.
   - Next experiment: reject PRs without schema review, query-plan review, and preflight records.

2. Topic: Standardize query-stream expectation envelope definitions across services.
   - Why now: envelope drift thresholds vary by team.
   - Expected impact: more consistent cross-service reliability.
   - Next experiment: pilot shared envelope schema in one additional graph-backed service.

---

## Delegation-Derived Backlog Item (Sample)

This example shows a single reflection backlog item generated from delegation telemetry.

- Objective context: Improve `/v1/recommendations` reliability and latency under high fan-out traversals.
- Delegation evidence refs: `lane-query-tuning`, `lane-integration-tests`, `lane-load-validation`.
- Triggered signatures: `REWORK_LOOP`, `PROOF_AMBIGUITY`.
- Observed pattern: implementation lane repeatedly changed query shape before completing plan-level query-stream preflight checks.

Backlog item:

- Title: Enforce pre-coding discovery completion before graph-query implementation
- Track: `abstract-method`
- Evidence scope: `cross-project`
- Split handling: `paired`
- Applicability realm: `discipline-general`
- Applicability signal: `both`
- Cost impact: 2 rework cycles, 1 delayed validation cycle, ~1 day slip in release candidate hardening.
- Action taken (initial): Added checklist requirement in planning doc.
- Expected effect: Reduce query-shape rework and avoid late detection of stream-expectation drift.
- Next validation probe: For next 3 delegated graph-query objectives, require recorded schema review + query-plan review + preflight results before any code lane starts; compare rework count vs prior cycle.
