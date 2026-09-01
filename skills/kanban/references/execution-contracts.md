# Execution Contracts

Read this reference when starting autonomous work, selecting gates, accepting
specialist handoffs, routing rework, or closing non-trivial work.

## Autonomy Envelope

Every autonomous run has one immutable envelope. It defines execution mode,
allowed tools and paths, network policy, step/time/retry/concurrency budgets,
approval-required action classes, and stop conditions. A worker may consume but
not expand it. Expansion requires a recorded human decision and a new run or
envelope version issued by the coordinator.

## Evidence Manifest

Evidence is revision-bound data, not an agent success claim. Record criterion,
artifact, exact revision or digest, probe, result, producer, environment,
location, content hash when practical, and associated gate. A passing gate does
not replace criterion evidence; passing evidence does not replace an applicable
independent gate.

## Specialist Handoff

Validate federated results against
[`specialist-handoff.schema.json`](specialist-handoff.schema.json). Version 2
separates gate identity, applicability, recommendation, and execution status:

```yaml
handoff_id: <stable idempotency id>
contract_version: "2"
specialist_class: <assigned class id>
specialist_class_version: <assigned class version>
engagement_role: <inform|produce|review>
worker_id: <producer identity>
gate_id: <selected gate or null>
applicability: <applicable|not-applicable|undetermined>
independent: <true|false>
intent_id: <id or null>
task_id: <id or null>
run_id: <id or null>
attempt_id: <id or null>
scope: <examined boundary>
permissions_used: []
sources: []
artifacts_observed: []
artifacts_changed: []
findings: []
obligations: [] # assurance only; task-specific tenet applications
guidance_proposals: [] # project principles or tenets; never auto-adopted
evidence: []
gate_recommendation: <pass|fail|blocked|not-applicable>
residual_risks: []
open_decisions: []
rework_destination: <stage or null>
status: <complete|rework|blocked|not-applicable|budget-exhausted|authorization-required>
```

A recommendation is advisory. It does not move the board, broaden permissions,
accept residual risk, or authorize delivery. The interchange schema defines
transport shape; successful atomic ingestion into normalized Kanban tables is
the authoritative acceptance event. Use
[agent-handoff-migration.md](agent-handoff-migration.md) to update older agent
output habits; legacy documents are not accepted.

Validate and ingest with `handoff validate` and `handoff ingest`. Schema-valid
documents may still fail semantic checks for unknown or mismatched workflow
ids, unassigned or stale specialist class, invalid result combinations, inadequate
independence or evidence, unauthorized permissions, or invalid rework routing.

## Enforcement ownership

SQLite constraints, foreign keys, and triggers are authoritative for
deterministic record and cross-record invariants. They enforce transition and
WIP limits; active-run envelopes; gate, evidence, decision, specialist, and
handoff relationships; immutable envelopes; and intent-realization conditions
even when a client writes directly to the database. The helper parses external
documents, selects operations, assembles transactions, and converts database
rejections into useful command errors. Do not reproduce a database-enforceable
rule only in a client. Keep contextual judgments—applicability, material risk,
specialist selection, source quality, and acceptance—outside SQL and persist
their results for the database to constrain.

## Lifecycle And Capability Map

The durable workflow has six stages. A specialist class may inform a choice,
produce an artifact,
evaluate a gate, or do both in separate attempts; skills are not automatically
mandatory serial stages.

The coordinator selects required expertise using
[specialist-coordination.md](specialist-coordination.md), persists each class
and gate assignment, and delegates the stored natural-language role context.
It does not route by installed skill name.

| Stage | Required outcome | Typical producer | Conditional evaluators |
| --- | --- | --- | --- |
| Discover | evidence-backed goal/product contract and material decisions | product discovery or coordinator | research readiness, security/privacy |
| Design | traceable design, slices, proof strategy, and accepted decisions | software architecture or task designer | independent design validation, security, supply chain |
| Implement | bounded artifact conforming to the accepted slice | software delivery or domain implementer | style, systems compatibility |
| Verify | deterministic revision-bound criterion evidence | implementer pre-check plus fresh evaluator | security, supply chain, domain validation |
| Deliver | controlled, reversible candidate and authorization record | coordinator or release mechanism | production readiness, security, supply chain |
| Observe | operational outcome and learning evidence | operator or coordinator | operational observation, reflection |

## Gate Selection

Select gates during triage from risk and scope. Expected types are product
contract, research readiness, architecture/design validation, implementation
verification, security/privacy, supply chain, independent review, delivery,
production readiness, and operational observation. An evaluator—not the
coordinator acting on its behalf—records `not-applicable` with rationale.
For governed work, profile the work and freeze an assurance/control review
plan. Every active class appears for both purposes. The invariant fallback is
required; only a pinned policy rule may create a pre-dispatch exception.
Assurance must complete before substantive production when a frozen plan
exists. Control reviewers independently pass, fail, block, or justify
`not-applicable` before acceptance. A scope-hash change stales the plan.

The plan also freezes an effective guidance snapshot. Read
[built-in-quality.md](built-in-quality.md) when constructing the worker context
or resolving assurance. Required tenets block Active until they become concrete
production obligations, valid inheritance, attributable not-applicability, or
an authorized exception. Planned or blocked obligations and unresolved
stop-quality signals block Done.

Research readiness includes reuse assessment. Before custom implementation,
inspect project-local capability, platform primitives, maintained open-source
libraries and templates, and standards. Record candidates, criteria, rejected
alternatives, and the verified gap. Mechanical execution may reuse an accepted,
fresh assessment; a new mechanism or materially changed premise may not.

## Rework

Route a defect to the earliest stage that can repair it: unclear value or
requirements to Discover; structural or contract defects to Design;
implementation defects to Implement; inadequate probes to Verify; release or
operational preparation defects to Deliver. Goal changes, authority decisions,
and risk acceptance return to the human decision protocol.

The detailed retry checkpoints in `autonomous-loop.md` remain an optional
playbook. The stages above are canonical. `delegation.md` applies only when work actually uses multiple lanes;
it does not make delegation mandatory.

## Durable Run Semantics

Record run and attempt ids, checkpoints, cancellation request and
acknowledgement, and external side-effect receipts. Retry only actions known to
be repeatable or protected by an idempotency key. Resume from persisted state;
conversation memory is never proof that an operation completed.
