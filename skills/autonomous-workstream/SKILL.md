---
name: autonomous-workstream
description: Use when a well-defined Kanban objective should continue executing through detached background workers while the foreground conversation remains available for decisions, status, and monitoring.
---

# Autonomous Workstream

This skill supplies the live supervisor and worker runtime for Kanban. It does
not create a second durable workflow database. The Kanban helper persists
intents, tasks, task states, dependencies, checks, evidence, events, guidance,
references, and pull capacity. The supervisor is a long-lived live process,
not a durable Kanban object. Worker sessions, heartbeats, attempts, and
checkpoints are ephemeral runtime state; replacement reconstructs work from
the durable task record and live repository state.

For live progress, lease renewal, timeout, and recovery messaging, read
`kanban/references/coordination-protocol.md`.

Before scheduling or dispatching, read `kanban/references/pull-flow.md` for
the canonical pull, prioritization, WIP, backpressure, and worker-demand
contract. Do not reconstruct that contract from memory or from CLI help.

When the selected agent platform offers detached jobs or background sessions,
also read `references/runtime-adapters.md`. Use the platform adapter for
dispatch and monitoring; retain the same Kanban lease and worker contracts.

## Role topology

Use one long-lived supervisor process or session plus dynamic specialist lanes:

- a supervisor monitors task states, review queues, pull leases, WIP, and
  backpressure, and continuously schedules the next action;
- Review lane: assurance/control workers perform task-bound review only;
- Implementation lane: implementation workers perform task implementation only;
- preparation/refinement/research and validation lanes are created only when
  pullable work requires them. Ready replenishment belongs to a
  research-capable preparation worker, not the low-cost supervisor.

An assurance/control worker may perform both functions for the same task and
may serially review multiple compatible tasks. It must not implement a task it
reviews. Do not launch one worker per criterion by default.

## Model and reasoning allocation

The coordinator is a routing and state-management role, not the primary
problem solver. Run the coordinator thread on the lowest-cost, lowest-token,
lowest-reasoning model that can reliably inspect Kanban status, rank eligible
work, issue or renew leases, dispatch workers, and report exceptions. Do not
use a high-reasoning model for routine queue polling, lease maintenance,
serialization, or status reporting.

Select each worker's model and reasoning level from the assigned work, not from
the overall workstream. Use the least expensive tier that can satisfy the
task's uncertainty and consequence:

- **mechanical:** status inspection, deterministic transformation, bounded
  validation, evidence collection, and other clearly specified work;
- **bounded:** ordinary implementation, focused research, or a well-defined
  specialist check with clear acceptance criteria;
- **complex:** ambiguous design, cross-component integration, novel diagnosis,
  multi-source synthesis, or assurance/control work requiring substantial
  judgment;
- **high-risk:** security-sensitive, irreversible, safety-critical,
  externally consequential, or otherwise high-residual-risk work requiring
  the strongest available reasoning and an appropriately qualified specialist.

Start at the lowest applicable tier. Escalate only when the task exhibits
material ambiguity, failed validation, repeated rework, contradictory
evidence, a newly discovered dependency, or risk beyond the current tier.
Escalation should apply to the smallest affected worker or slice, not to the
whole workstream. If decomposition can reduce complexity, decompose before
raising the model tier.

The coordinator may temporarily escalate for an exceptional scheduling or
authority decision, but must return to its low-cost default afterward. Worker
reuse is preferred when the same model tier, specialist role, task boundary,
and context remain valid; do not reuse a cheap worker across a task whose
complexity or authority requirements have materially changed.

Every dispatch should carry a compact model-selection rationale: task
complexity tier, required reasoning level, specialist role if any, and the
condition that would justify escalation. Do not silently assign the maximum
model or reasoning level to every worker.

Prefer a platform-native detached job when it supports the required briefing,
status, follow-up, cancellation, and artifact handoff operations. Do not
assume that a detached job is a persistent server, shared workspace, or
surviving process; use only the lifetime and isolation guarantees documented by
the adapter.

## Queue-draining loop

Before dispatching the first worker for an execution request, establish the
supervisor lifetime. If background continuation is requested, submit and
verify one detached supervisor job through the runtime adapter; retain its job
identity and task/lease scope in the foreground handoff. If the adapter cannot
provide a live detached job, continue the loop in the foreground and say so;
do not imply that work will continue after the turn ends.

Every supervisor wake performs a queue-drain scheduling pass:

1. walk the active board with `status --json`, inspecting only Ready, Active,
   Review, or their configured policy equivalents; exclude Backlog and terminal
   states from the walk;
2. refresh active pull-capacity leases and expose each walked state's occupancy,
   WIP limit, fullness, and overage;
3. prioritize clearing WIP overage and actionable downstream work;
4. when Ready is below its finite WIP limit, dispatch bounded,
   research-capable refinement workers for the most valuable eligible Backlog
   candidates; the supervisor selects and briefs this work but does not perform
   its research or refinement itself;
5. collect work from configured review/validation states before admitting new
   implementation when those states are the active constraint;
6. prioritize the smallest unblocker that releases downstream pull capacity;
7. group compatible assurance/control checks for serial specialist reuse;
8. pull the next most-ready tasks only when downstream capacity exists;
9. start only the workers necessary for current pullable work, each with a
   bounded next action, expected progress checkpoint, and compact authority
   briefing;
10. after every completion, rework result, validation result, or capacity release,
   repeat the pass.

The walk also runs periodically while workers remain active, not only after a
worker event. A Ready deficit is a pull signal for research and refinement, not
permission to start unbounded refinement or implementation work. Cap dispatch
by the deficit, defined worker demand, available authority, and downstream
flow. The refinement worker must review task- and intent-linked research,
gather additional sources when needed, evaluate reusable open-source libraries
and existing patterns, and record the rationale before moving the task to
Ready.

Continue until no unblocked pullable work remains, or work is permission-gated,
manually reserved, externally blocked, or explicitly deferred. Completion of a
single slice is a scheduling event, not a reason to stop.

The supervisor may stop only after a final pass confirms all of the following:
no actionable review/validation item remains, no recoverable stale worker
remains, no dependency-unblocked candidate is stranded in Backlog, Ready, or
an entry state, and no detached worker or supervisor job is still active. An
empty Ready queue alone is never a completion signal.

## Pull and backpressure

Read the shared pull-flow contract before this pass. Its local operational
rules are: downstream capacity pulls work; full downstream WIP creates a
priority interrupt rather than a hard admission stop; outcome advancement
precedes shortest-job preference; aging prevents starvation; WIP limits are
soft flow budgets and do not prescribe agent counts; and compatible workers
should be reused serially when demand permits. A full state is not a task
blocker.

## Task worker demand

The task’s worker-demand contract defines serial, partitionable, or fan-out
work, explicit work units, minimum/target/maximum workers, reuse policy,
isolation, and aggregation. Do not create arbitrary parallel workers merely
because capacity is available. Additional workers require already-defined
independent work units.

Every worker claim must name one bounded next action and an expected checkpoint;
split or refine work that cannot be expressed that way before dispatch.

## Worker briefing and live progress

Every dispatch briefing includes the task and lease IDs, repository/path scope,
objective, acceptance and validation criteria, current revision, required
output, permitted tools, prohibited side effects, approval boundaries, stop
conditions, model/reasoning tier, bounded next action, and expected checkpoint.

Workers report compact live deltas containing the task ID, lease ID, phase
(`working`, `waiting`, `blocked`, or `complete`), meaningful change, artifact
or evidence reference, blocker, and next bounded action. Heartbeats establish
liveness only. The supervisor keeps these live signals in memory; only
meaningful milestones, outcomes, and recovery decisions become task events.

## Recovery

The supervisor must not depend on persisted run records. If a session dies or
a lease expires, stop dispatching through that lease, allow its capacity
reservation to release, and do not silently reassign the task. Inspect the
task’s current state, owner, dependencies, latest meaningful task events,
checks, evidence, and current filesystem/version-control state. Decide whether
to resume, rework, review, or reassign, then record that recovery decision as a
task event before dispatching again.

Heartbeats and chat are liveness signals, not durable proof. Durable events
should record meaningful milestones, blockers, next actions, state transitions,
review outcomes, and evidence references.

Meaningful progress includes a worker report, completed research, test
execution, evidence collection, review/check recording, artifact creation, or
a meaningful repository change. A filesystem delta is not required for
read-only research, validation, or assurance work. If a worker is responsive
but cannot continue, recover it with a bounded requeue or fresh briefing and
record the recovery event before dispatching again.

## Assurance and control

When a task enters a state whose policy requires assurance, the Kanban helper
asserts that every active specialist role has a required assurance check.
Review workers consume those checks and any task-specific control checks. A
worker may satisfy several role checks when qualified, but implementation
remains isolated from assurance and control.

Terminal states require all checks and evidence specified by their state policy
to qualify before completion.

## Foreground contract

The foreground conversation remains available for human decisions, authority,
status, approvals, and exceptions. It should not need to prompt the supervisor
to clear a full review queue or continue a viable backlog. Report the current
queue, active lanes, backpressure, next pull, blockers, and why execution
stopped when no work is pullable.

Use the Kanban command service only as the durable transaction boundary:
obtain scheduler status, select or claim work, reserve or release pull
capacity, and record meaningful task events, checks, or evidence. Keep worker
liveness, lease-renewal intent, worker reuse, and dispatch decisions in the
supervisor-to-worker communication path. A missing heartbeat is handled by
letting a lease expire and recovering from durable task state; it does not
justify a heartbeat table or persisted run record.

Before acting, classify the foreground request as status, planning/refinement,
or execution. Status is read-only. Planning/refinement may prepare work but
does not implement it. Execution continues through implementation, review,
validation, and rework until no pullable work remains or an explicit stopping
condition applies.
