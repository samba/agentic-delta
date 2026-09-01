# Delegation

Use this reference when the user says `start background work`, `run workstream`,
`pause background work`, `resume background work`, `stop background work`, or
otherwise asks for background, queued, autonomous, or parallel work.

Always read `references/commands.md` first. Deprecated workflow phrases must
warn and stop before this workflow starts.

Read `references/standard-of-excellence.md` for every delegated durable goal.
Goal persistence and safe queueing happen before the fast foreground handoff.

For software-development objectives that need an evidence-gated autonomous
stage flow, also read `references/autonomous-loop.md`. That reference defines
foreground/background separation, stage-owned applicability decisions,
producer-owned handoff checks, design validation before implementation, and
rework routing.

`start background work <goal>` means: queue and dispatch background execution,
report what is queued or running, then return foreground control. The foreground
thread must not perform substantive implementation after dispatch.

`run workstream <goal>` means: autonomous queue-drain mode. Keep a coordinator
lane active while pullable work remains. After each proof-backed closure, the
coordinator must reevaluate Review, Active, Ready, and planned intents; dispatch
the next unblocked work that satisfies WIP/readiness/research/ownership gates;
and repeat until only manual-review-reserved, externally blocked,
permission-gated, or categorically deferred work remains.

`map workstream <goal>` is not an execution command. It belongs to planning:
report the viable queue, dependency sequence, parallel lane groups,
research-first gates, validation gates, explicit exclusions, stop conditions,
and approval needed to proceed. Do not dispatch execution lanes from this phrase
alone.

## Foreground And Background

Foreground work is the dispatcher and user-facing control plane. Use it for
goal intake, short interview cycles, autonomy boundaries, approval requests,
status summaries, exception handling, and continued planning while background
workers execute.

Background work is the execution plane. Keep a coordinator lane active for every
delegated objective. The coordinator sequences stages, enforces WIP limits,
tracks blockers and heartbeats, collects stage records, and routes rework. It
must not bypass a later stage on behalf of that stage's agent.

## Fast Handoff

Foreground work is a dispatcher. Return control within 1 minute when background workers are available.

Before the first return, do only enough to queue work safely:

- parse the request;
- load project kanban state when present;
- create or update minimal coordinator/research/planning cards;
- identify immediate safety, permission, or write-scope blockers;
- dispatch the first background lane, unless the user only asked to `map
  workstream` and has not yet approved execution.

Move deep analysis, research, decomposition, and implementation-path selection into background cards. Do not ask clarifying questions before the first return unless the request is impossible or unsafe to queue without the answer.

When the delegated objective involves operational risk, security hazards, privacy controls, performance-sensitive architecture, data movement, backup/restore, network isolation, identity, or secrets, dispatch a research or design lane before implementation lanes. Implementation should wait until research has identified proven patterns, failure modes, validation requirements, and the recommended contract, and until the design validation gate has passed or recorded a valid skip for a trivial task. Research lane completion must persist findings, conclusions, and design/implementation implications as evidence for downstream lanes.

The first response should name queued/active card ids, what is running, known blockers, and when the coordinator will report back or ask questions. For `map workstream`, the first response is the scope report and approval request; do not report execution as running until approval is given.

After `start background work` or `run workstream`, the foreground thread may
only report dispatch state, ask blocking questions, request approval, or handle
exceptions. It must not continue implementing the requested objective in the
active thread.

## Lane Types

Use a queue of lanes rather than one monolithic task when work can be split safely:

- `coordinator`: owns progress probing, criteria refinement, risk tracking, pattern checkpoints, and final review.
- `research`: owns authoritative source review and candidate-solution discovery.
- `planning`: owns decomposition, persisted plans, readiness estimates, and interview questions.
- `design`: owns design draft packets, architecture fit, integration paths, slice plans, and design assumptions.
- `design-validation`: owns pre-implementation design validation and stage/category applicability records.
- `implementation`: owns a disjoint file/path or behavior slice.
- `validation`: owns proof gathering, tests, diagnostic review, and completion evidence.
- `reviewer`: owns acceptance checks for high-risk or formerly ambiguous work.

Keep at least one coordinator lane for active delegated objectives. Queue implementation only after research/planning/design work has produced enough certainty for the start gate and the design-validation stage has run.

## Startup Sequence

When a task is first delegated:

1. Restate the goal as one sentence.
2. Load or initialize project kanban state and capture or locate the durable intent.
3. Acknowledge its intent id and create the minimum coordinator, research, or planning cards needed to reason safely.
4. If the work has sensitive operational, security, privacy, or performance tradeoffs, create a research-first prerequisite and do not queue implementation ahead of it.
5. Dispatch background lanes and return foreground control within 1 minute.
6. In background, research proven options before expanding implementation;
   persist findings, assumptions, conclusions, and downstream design or
   implementation implications into kanban records for later human review.
7. Draft or update the design packet for non-trivial software work.
8. Run design validation before implementation. Each stage/category agent owns
   its applicability, canonical recommendation, execution status, and evidence.
9. Score complexity and ambiguity, then choose lane rigor.
10. Run the coupling preflight and define ownership boundaries.
11. Pull only ready cards into Active, respecting WIP limits and backfill goals.
12. Record applicable autonomy budgets and open human decisions; dispatch safe
    independent work while a non-global decision waits.

## Lane Contract

Autonomous lanes additionally receive the immutable autonomy envelope defined
in [execution-contracts.md](execution-contracts.md). Federated workers return
that reference's specialist handoff. Worker output is advisory until the
coordinator validates its contract and records the applicable gate result.

Each lane must have:

- explicit ownership scope and prohibited scope;
- one kanban column and owner;
- concrete pull criteria and exit criteria;
- entry criteria, applicability/skip criteria, and pre-handoff validation criteria;
- required validation and expected evidence;
- readiness/confidence assessment for implementation cards;
- blocker state or `none`;
- known risks and mitigations;
- complexity, ambiguity, lane rigor, and review rigor estimates;
- completion output: stage status, changed files when applicable, tests run,
  proof of exit criteria, commit hash or no-commit reason;
- for research lanes: sources consulted, findings, rejected alternatives, recommended hypothesis, validation method, and downstream task implications;
- for design and design-validation lanes: design packet, category decisions,
  rework routes, accepted residual risks, and implementation readiness;
- simplicity/idempotency/error-boundary check summary.

Do not accept lane closure when the completion payload is missing. Continue or retask the lane until evidence is explicit.

## Start Gate

Implementation cards require all of:

- explicit scope and non-goals;
- observable success criteria;
- resolved constraints, authority boundaries, permissions, and dependencies;
- a confirmed implementation and rollback/revert plan;
- a concrete validation strategy mapped to the success criteria;
- a passed design-validation record, or an explicit design-validation skip
  record for a trivial task whose criteria are met;
- confirmed plan.

Readiness percentages may summarize judgment but cannot satisfy or override a
missing entry artifact. The coordinator must cite the evidence for each gate.

Research, planning, clarification, and validation-design cards may run below this threshold when their purpose is to raise readiness. If a broad objective is not ready, split out the smallest planning or research card that can make it ready.

The coordinator may not skip stages by risk classification. Every expected
stage is evaluated and its agent records applicability, recommendation, and
status using its own criteria.

## Lane Cost Alignment

Use the lowest-cost lane that can do the work correctly:

- `light`: status checks, scans, blocker evaluation, queue updates, short validation reruns, triggering already-unblocked work.
- `medium`: local implementation with clear requirements and cheap validation.
- `high`: ambiguous scope, cross-file behavior, safety/security concerns, expensive validation design, or subtle acceptance criteria.
- `very-high`: broad architecture, cross-boundary orchestration, destructive/runtime-sensitive behavior, or high cost of accepting incomplete work.

For high or very-high work, start with a planner lane that splits the objective into smaller cards with explicit ownership, requirements, validation, dependencies, and reviewer needs. Use dedicated reviewer lanes when completion criteria are subtle or risk is high.

## Coupling And Parallelism

Run a coupling preflight before dispatch:

- `disjoint`: split into parallel lanes by ownership boundary.
- `partially-coupled`: use phases, usually foundation/scaffold before caller cutover.
- `tightly-coupled`: keep one implementation lane with checkpoints.

When projected write surface is large, record either the lane split or why a single lane is safer. Do not parallelize across shared write scopes without a clear ownership boundary.

## Clarification Policy

Default to queue-first clarification. Ask immediately only when:

- safety, security, data loss, cost, or permission boundaries are unclear;
- plausible interpretations would create incompatible write scopes;
- the task cannot be represented as a safe card without the answer;
- the user explicitly asks to decide the plan before background work starts.

Otherwise, continue under the recommended default, record the assumption, and batch non-urgent questions for the next status/progress report.

## Validation And Closure

Before dispatching validation expected to exceed 30 seconds, present the expected test path for approval. Track unvalidated high-cost follow-up as kanban cards rather than hiding it in completion notes.

For long-running lanes, require periodic heartbeats with progress, blocker state, next action, and ETA to next checkpoint.

Move completed implementation to `Review`, not `Done`. Move to `Done` only after completion proof is accepted and integration risks are closed or queued.

## Rework Records

When a stage rejects a handoff or cannot complete its pre-handoff validation,
route the task to the responsible owner stage instead of retrying blindly in the
current stage. Prefer first-class helper fields when available. Until the helper
schema supports dedicated stage records, persist rework and applicability
decisions as task events or metadata with:

```text
stage=<stage>
applicability=applicable|not-applicable|undetermined
gate_recommendation=pass|fail|blocked|not-applicable
status=complete|rework|blocked|not-applicable|budget-exhausted|authorization-required
failure_class=<class>
returned_to_stage=<stage>
repair_required=<specific repair>
evidence=<proof or observation>
retry_count=<count>
resume_condition=<condition>
```

Use the rework routing and retry policy in `references/autonomous-loop.md` for
software-development objectives.

## Telemetry And Pattern Checkpoints

Capture lightweight telemetry at lane checkpoints:

- `replan_count`;
- `blocker_count`;
- `blocker_age_max_min`;
- `rework_count`;
- `validation_fail_count`;
- `validation_ambiguous_count`;
- `handoff_count`;
- `user_correction_count`.

Use these pattern signatures:

- `SCOPE_THRASH`: `replan_count >= 2`.
- `BLOCKER_RECUR`: `blocker_count >= 2` or `blocker_age_max_min > 30`.
- `REWORK_LOOP`: `rework_count >= 1` and `validation_fail_count >= 1`.
- `PROOF_AMBIGUITY`: `validation_ambiguous_count >= 2`.
- `COORD_OVERHEAD`: `handoff_count >= 3`.
- `GUIDANCE_MISMATCH`: `user_correction_count >= 2` in the same objective.

Run a pattern checkpoint when one signature appears in two or more lanes in the same objective, one lane has two or more signatures, or the same signature repeats across two queue cycles. At a checkpoint, pause new implementation, classify the root cause, choose a simpler execution pattern or proven analog, define one validation probe, then resume.

Create backlog candidates from repeated patterns only when they are actionable and not project-specific leakage. Notify the user with the candidate title, track, and evidence refs.

## Worker Prompt Requirements

Every worker prompt must include:

- objective and card id;
- allowed and prohibited scope;
- exit criteria;
- validation commands or evidence;
- required completion output;
- style gate: aggressive pursuit of logical simplicity, shallow control flow, idempotent operations by default, and error handling pushed to the lowest safe layer.
