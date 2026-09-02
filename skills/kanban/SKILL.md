---
name: kanban
description: Use when capturing durable goals, planning or prioritizing work, maintaining project state, reporting status, refining a backlog, or coordinating bounded autonomous software work through research, decisions, gates, evidence, review, delivery, and learning.
---

# Kanban Coordinator

This is the canonical coordinator for durable objectives and work-item state.
It persists intent, selects the least-complex adequate workflow, issues bounded
work, accepts specialist evidence, enforces gates, routes rework, and reports
outcomes. It does not replace domain specialists or human authority.

For every durable objective, read the
[standard of excellence](references/standard-of-excellence.md). For autonomous
runs, gates, specialist results, rework, or closure, also read the
[execution contracts](references/execution-contracts.md). These two references
are normative; the
[semantic rule inventory](references/semantic-rule-inventory.md) resolves
ownership and legacy terminology.

Autonomous execution is provided by the separate `autonomous-workstream`
skill. Kanban remains authoritative for intents, tasks, dependencies, WIP,
eligibility, allocation constraints, evidence, and closure. A supervised run
consumes those policies and writes execution state back through the helper;
kanban remains usable for manual planning and coordination.

## Intent And State

Treat an explicit durable objective—such as “my goal is”, “build”, “achieve”,
or “run this workstream”—as a persistence request unless the user marks it
exploratory or plan-only. Before substantive autonomous execution:

1. capture the objective, known success criteria, constraints, non-goals,
   autonomy mode, approval boundaries, and stop conditions;
2. acknowledge the intent id;
3. research and refine before creating premature implementation tasks;
4. enroll every active specialist class so project principles and actionable
   tenets can guide the earliest work;
5. link every executable task to at least one intent.

An intent is `captured`, `researching`, `refining`, `planned`, `deferred`, or
`closed`; closure is `realized` or `rejected`. A work item is `Backlog`,
`Ready`, `Active`, `Blocked`, `Review`, `Done`, or `Deferred`. `Done` applies to
accepted work; an intent is realized only when all required linked work and
outcome criteria are satisfied.

If persistence is unavailable, maintain an explicit in-session contract and
disclose the degraded durability. Never imply that state was persisted.

## Coordinator Invariants

- Preserve `goal -> research/decision -> design -> task -> validation criterion
  -> exact evidence` traceability.
- Research begins locally, then uses current authoritative sources. Before a
  custom mechanism, assess platform primitives, maintained open source,
  templates, and standards; retain candidates, rejected alternatives, and the
  verified capability gap.
- Persist material human decisions. Ask only after safe inspection and research
  cannot resolve them; never infer approval for privileged, destructive,
  externally consequential, goal-changing, or high-residual-risk actions.
- Before dispatch, record an immutable autonomy envelope covering paths, tools,
  network, credentials, side effects, time/cost, concurrency, retry, approval,
  cancellation, and stop conditions. A worker cannot expand it.
- Enforce WIP and dependency readiness. Use isolated write ownership for
  concurrent work and avoid delegation when a deterministic operation or
  single bounded lane is sufficient.
- A request to review an existing codebase invokes every enrolled specialist
  against the project goal. Register a discovered bug immediately, obtain every
  enrolled specialist disposition, and prioritize it with remaining goal work
  before creating its governed corrective task.
- Select expected gates from risk and scope. Each evaluator owns its
  applicability and recommendation; the coordinator may not fabricate a pass
  or `not-applicable` result.
- Bind evidence to criteria and exact artifact revisions. Agent confidence,
  self-report, or passing tests alone cannot close non-trivial work.
- Require a fresh independent review for non-trivial work and route defects to
  the earliest stage able to repair them. Bound retries and checkpoint repeated
  failure patterns rather than repeating unchanged attempts.
- Keep validation debt, residual risk, exceptions, deferred work, and scope
  drift explicit. They block closure unless accepted by authorized policy or a
  recorded human decision.
- Record cancellation acknowledgement and external side-effect receipts.
  Resume from persisted state, never conversation memory.
- Record material outcomes and corrections in the canonical learning store.
  Learning may propose but cannot silently change governing controls.

## Operating Sequence

Use the least serial execution consistent with dependencies and risk:

1. Capture and triage the intent, ambiguity, risk, budgets, and authority.
2. Discover local context, sources, established solutions, and decisions.
3. Produce and independently validate a traceable design and proof strategy.
4. Create coherent, bounded, reversible implementation slices.
5. Execute ready work within WIP and autonomy limits.
6. Verify exact revisions against acceptance criteria and applicable gates.
7. Independently review and route bounded rework when necessary.
8. Deliver only with required authority, safety, rollback, and readiness proof.
9. Observe outcomes, close only on complete evidence, and record learning.

Research, refinement, and independent read-only lanes may overlap when their
dependencies and write ownership permit it. Numbering expresses causal
obligations, not mandatory wasteful serialization.

## Conditional References

Load only what the current operation needs:

- [board walk](references/board-walk.md): status reporting, WIP, movement,
  review, and closure checks;
- [backlog refinement](references/backlog-refinement.md): refining ideas into
  ready, evidence-backed work;
- [execution contracts](references/execution-contracts.md): autonomous runs,
  stage/gate selection, evidence, specialist handoffs, rework, and recovery;
- [specialist coordination](references/specialist-coordination.md): selecting
  implementation-neutral expertise, assigning it to gates, and constructing
  delegated role context;
- [built-in quality](references/built-in-quality.md): versioned principles and
  tenets, frozen guidance, production obligations, reusable assurance,
  quality signals, constraints, and kaizen experiments;
- [project specialists and bugs](references/project-specialists-and-bugs.md):
  the canonical common mechanics for early enrollment, guidance proposals,
  comprehensive existing-codebase review, and specialist-informed bug triage;
- [agent handoff migration](references/agent-handoff-migration.md): updating
  agents that emit older handoff vocabulary or unstructured arrays;
- [delegation](references/delegation.md): only for multi-lane or background
  coordination;
- [autonomous-loop compatibility](references/autonomous-loop.md): legacy stage
  records or its detailed retry/pattern checkpoints;
- [validation contracts](references/validation-contracts.md): selecting a
  domain-specific validation output;
- [intents and migration](references/intents-and-migration.md): legacy backlog
  migration and reference linkage;
- [commands](references/commands.md): exact helper syntax;
- [source register](references/source-register.md): adding, refreshing, or
  superseding a governing source or principle.

For detached, continuously resumable execution, load the
`autonomous-workstream` skill. It owns the supervisor and worker lifecycle,
event-driven dispatch, worker affinity and context reuse, leases, checkpoints,
recovery, and run-level resource controls.

## Deterministic State Helper

Use `scripts/kanban.py` rather than editing the database directly. Initialize
with `init`; validate with `validate`; use the typed intent, task, decision,
run, envelope, gate, evidence, receipt, reference, learning, and metric commands
documented in `references/commands.md`.

Specialist documents must pass `handoff validate` and then `handoff ingest`.
Only the committed receipt establishes acceptance; the helper atomically
normalizes the handoff, evidence, sources, artifacts, findings, risks,
decisions, gate result, and learning event.

The helper is authoritative for enforced transitions and atomic records. Do not
work around a failed constraint by editing SQLite manually. A tool limitation
is a blocker or a reason to propose a reviewed migration, not permission to
weaken policy.

## Human Decisions And Status

For a material decision, persist one bounded question with viable options when
known, a recommendation/default, impact of delay, and safe parallel work. After
resolution, retain the answer, rationale, decider, and affected artifacts and
update dependent work before resuming. Use clarification records only for
factual unknowns.

Status reports distinguish intents from work items and include active work,
blocked work and exact unblock condition, review/validation state, open human
decisions, WIP pressure, and the next pull candidate. Do not describe internal
agent assignment as human ownership unless asked.

## Closure

Before moving non-trivial work to `Done` or realizing an intent, require:

- satisfied acceptance criteria and complete revision-bound evidence;
- all expected gates passed or evaluator-owned `not-applicable` records;
- accepted independent review and resolved rework;
- authorized delivery/readiness evidence when applicable;
- explicit residual risk, exceptions, validation debt, and deferred work;
- recorded outcome and learning events.

Report partial or blocked outcomes honestly. Do not convert incomplete proof,
budget exhaustion, or a plausible implementation into success.
