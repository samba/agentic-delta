# Autonomous Software-Development Loop

Use this reference when the work is a software-development objective that should
advance through a background, evidence-gated loop. The loop applies to product,
library, infrastructure, data, documentation, and skill implementation work; do
not specialize the loop around skill editing.

## Foreground And Background

Keep the foreground thread for goal intake, short interview cycles, planning
approval, autonomy boundaries, status summaries, exceptions, and new planning
while the background coordinator continues execution.

Run software work in background lanes whenever delegation or queued execution is
available and the user has approved autonomous execution. The coordinator owns
queue sequencing, WIP limits, rework routing, heartbeats, blocker state, and
closure proof. Stage agents own the judgment for their stage.

## Stage Flow

Use this default flow unless the project declares a stricter process:

```text
Goal Intake -> Interview -> Discovery/Research -> Design Draft ->
Design Validation -> Implementation -> Runtime Verification -> Review ->
Commit/PR
```

Each stage follows:

```text
Entry Check -> Applicability Decision -> Work Or Skip -> Pre-Handoff
Validation -> Handoff Package
```

Every stage must run. A previous stage may recommend risk level or likely
applicability, but it must not bypass a later stage. Only the agent responsible
for a stage may classify that stage as not applicable.

## Stage-Owned Applicability

Each stage records one of:

- `applied`: the stage performed substantive work or validation.
- `skipped-not-applicable`: the stage's own documented skip criteria were met.
- `blocked`: required inputs, permissions, or environment are missing.
- `rework`: the task is returned to the responsible earlier stage.

A skip is an executed stage. The stage must record the criteria, evidence, and
why the remaining risk is acceptable for this task. Examples:

- Security may skip a docs-only wording change after confirming no code, data,
  auth, secrets, dependency, network, deployment, or operator surface changed.
- Performance may skip a local help-text change after confirming no runtime
  path, algorithm, concurrency, IO, caching, or scaling behavior changed.
- Design validation may reduce rigor for tiny local changes that follow an
  existing pattern, but non-trivial implementation work still needs a design
  validation record.

## Producer-Owned Handoff Quality

A stage may not hand off work until it has run its own pre-handoff validation
and produced the evidence expected by the receiving stage. If the producing
stage cannot satisfy its handoff contract, it must route the task to the
responsible earlier stage or mark itself blocked; it must not pass an incomplete
artifact forward and rely on the next stage to discover the deficiency.

## Stage Artifacts

Use compact artifacts with enough structure for the next stage:

- Goal Intake: goal contract with objective, users, non-goals, constraints,
  autonomy boundaries, stop conditions, and acceptance criteria.
- Interview: clarified goal contract plus unresolved questions and default
  assumptions.
- Discovery/Research: evidence brief covering project-local precedent, relevant
  design patterns, candidate libraries/tools, rejected alternatives, license or
  maintenance caveats when relevant, selected approach, and uncertainty.
- Design Draft: design packet with architecture fit, data/control flow,
  interfaces, dependencies, implementation slices, assumptions, risks, and
  rollback or revert points.
- Design Validation: validation report with applied/skip records for the
  categories below, pass/fail/partial status, rework routes, and accepted
  residual risk.
- Implementation: changed files, behavior summary, design-drift notes, local
  checks, and residual risk.
- Runtime Verification: proof bundle with commands, outputs, fixtures,
  screenshots, logs, or other validation evidence.
- Review: accept/rework decision with severity-ranked findings and evidence.
- Commit/PR: release handoff with commit hash or no-commit reason, final tests,
  design/doc updates, and follow-up cards.

## Design Validation Gate

Design validation is mandatory before implementation for non-trivial software
work. It proves the design is clear, bounded, testable, safe enough, and worth
implementing now. It may route backward to Interview, Discovery/Research,
Design Draft, or Validation Strategy.

Always consider these categories:

- problem and scope: goals, users, use cases, non-goals, constraints,
  acceptance criteria, and autonomy limits;
- requirements traceability: requirement -> design decision -> implementation
  slice -> validation proof;
- architecture fit: existing patterns, module boundaries, data/control flow,
  interfaces, ownership, dependency direction, and integration handoffs;
- implementation slice plan: smallest coherent steps, dependency order,
  reversible checkpoints, and safe sequencing;
- test and validation strategy: unit, integration, end-to-end, fixture, golden
  output, benchmark, manual, screenshot, or other proof chosen by risk and
  behavior;
- maintainability and code style: simplicity, coupling, cohesion, naming, local
  conventions, API surface, and documentation impact;
- risk and tradeoff review: alternatives considered, assumptions, failure
  modes, mitigations, and residual risk.

Conditionally apply these categories when the task touches the relevant surface:

- security/privacy: auth, authorization, secrets, untrusted input, user data, or
  external exposure;
- data/schema/migration: persistence, migrations, backfills, data loss, or
  compatibility;
- performance/scale: latency, throughput, memory, concurrency, large datasets,
  caching, or algorithmic complexity;
- reliability/operations: retries, idempotency, observability, rollout,
  rollback, recovery, or dependency failure;
- compatibility/API contracts: public interfaces, CLI flags, file formats,
  protocol changes, or generated artifacts;
- compliance/licensing: regulated data, OSS licenses, audit evidence, or
  redistribution limits;
- UX/accessibility: user-facing flows, UI behavior, visual design, or assistive
  technology;
- supply chain: new dependencies, code generation, build tools, external
  services, or plugin/MCP registries;
- concurrency/distributed systems: races, locking, ordering, consistency, or
  partitions.

The stage agent for each category owns its own applicability decision. The
coordinator may not mark a category skipped on that agent's behalf.

## Rework Routing

When a stage fails, classify the deficiency and route to the stage responsible
for repair:

| Failed stage | Typical deficiency | Route back to | Repair |
| --- | --- | --- | --- |
| Interview | unclear goal, constraints, or acceptance criteria | Interview | ask targeted questions and revise the goal contract |
| Discovery/Research | missing facts, weak precedent search, uncertain library/tool choice | Discovery/Research | gather sources, compare options, record selected approach |
| Design Draft | incomplete structure, broad slice, unclear interface or flow | Design Draft | revise architecture, handoffs, slices, and assumptions |
| Design Validation | requirement mismatch, unresolved risk, weak proof plan | Design Draft or Discovery/Research | adjust design, narrow scope, add research, update risk treatment |
| Implementation | hidden dependency, design drift, code cannot follow design cleanly | Design Draft | revise slice, interface, handoff, or assumption |
| Runtime Verification | failing tests, ambiguous validation, missing coverage | Implementation or Validation Strategy | fix code, add lower-level tests, revise proof contract |
| Review | maintainability, security, style, or architecture issue | Implementation or Design Draft | fix local code or revisit structure |
| Commit/PR | final checks, docs, branch, or release hygiene fail | Implementation or Review | complete release hygiene and rerun closure proof |

Use stable failure classes:

```text
unclear-goal, missing-research, bad-design, overscoped-slice,
invalid-assumption, implementation-defect, missing-test, weak-validation,
design-drift, review-finding, release-hygiene, tooling-failure,
environment-failure
```

Record rework events with `failed_stage`, `failure_class`,
`returned_to_stage`, `repair_required`, `evidence`, `retry_count`, and
`resume_condition` when the board helper supports those fields; otherwise use a
task event or backlog note.

## Retry And Checkpoint Policy

Prefer bounded rework over linear retries:

- one local implementation defect may be fixed directly in implementation;
- two design-validation failures route to Discovery/Research unless the cause
  is purely documentation of an already-known design;
- two runtime-verification failures on the same behavior trigger validation
  strategy review and slice-size review;
- two review failures about architecture or coupling return to Design Draft;
- three total rework cycles trigger a pattern checkpoint and a user-facing
  options report.

At a pattern checkpoint, pause new implementation for the affected objective,
classify root cause, choose a simpler execution path or proven analog, define
one validation probe, then resume only after the repair artifact is updated.

## Scope Drift And Validation Debt

Classify implementation drift as:

- `within-slice`: proceed and record it;
- `needs-new-card`: create or propose a follow-up;
- `blocks-current-design`: route to Design Draft;
- `changes-goal`: route to Interview or user approval.

Do not hide validation debt in closure notes. If proof is incomplete, create or
retain explicit validation work with owner, due condition, missing evidence, and
acceptance rationale. Validation debt blocks `Done` unless the user or declared
project policy accepts the residual risk.
