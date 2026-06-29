# Delegation

Use this reference when the user asks for async, background, delegated, queued, autonomous, or parallel work.

## Fast Handoff

Foreground work is a dispatcher. Return control within 1 minute when background workers are available.

Before the first return, do only enough to queue work safely:

- parse the request;
- load project kanban state when present;
- create or update minimal coordinator/research/planning cards;
- identify immediate safety, permission, or write-scope blockers;
- dispatch the first background lane.

Move deep analysis, research, decomposition, and implementation-path selection into background cards. Do not ask clarifying questions before the first return unless the request is impossible or unsafe to queue without the answer.

The first response should name queued/active card ids, what is running, known blockers, and when the coordinator will report back or ask questions.

## Lane Types

Use a queue of lanes rather than one monolithic task when work can be split safely:

- `coordinator`: owns progress probing, criteria refinement, risk tracking, pattern checkpoints, and final review.
- `research`: owns authoritative source review and candidate-solution discovery.
- `planning`: owns decomposition, persisted plans, readiness estimates, and interview questions.
- `implementation`: owns a disjoint file/path or behavior slice.
- `validation`: owns proof gathering, tests, diagnostic review, and completion evidence.
- `reviewer`: owns acceptance checks for high-risk or formerly ambiguous work.

Keep at least one coordinator lane for active delegated objectives. Queue implementation only after research/planning has produced enough certainty for the start gate.

## Startup Sequence

When a task is first delegated:

1. Restate the goal as one sentence.
2. Load project kanban state when present.
3. Create the minimum coordinator, research, or planning cards needed to reason safely.
4. Dispatch background lanes and return foreground control within 1 minute.
5. In background, research proven options before expanding implementation.
6. Score complexity and ambiguity, then choose lane rigor.
7. Run the coupling preflight and define ownership boundaries.
8. Pull only ready cards into Active, respecting WIP limits and backfill goals.

## Lane Contract

Each lane must have:

- explicit ownership scope and prohibited scope;
- one kanban column and owner;
- concrete pull criteria and exit criteria;
- required validation and expected evidence;
- readiness/confidence assessment for implementation cards;
- blocker state or `none`;
- known risks and mitigations;
- complexity, ambiguity, lane rigor, and review rigor estimates;
- completion output: changed files, tests run, proof of exit criteria, commit hash or no-commit reason;
- simplicity/idempotency/error-boundary check summary.

Do not accept lane closure when the completion payload is missing. Continue or retask the lane until evidence is explicit.

## Start Gate

Implementation cards require all of:

- confidence `>=99%`;
- scope readiness `>=99%`;
- success criteria readiness `>=99%`;
- constraints/requirements readiness `>=99%`;
- implementation plan readiness `>=99%`;
- confirmed plan.

Research, planning, clarification, and validation-design cards may run below this threshold when their purpose is to raise readiness. If a broad objective is not ready, split out the smallest planning or research card that can make it ready.

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
