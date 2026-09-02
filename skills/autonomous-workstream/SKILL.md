---
name: autonomous-workstream
description: Use when a well-defined kanban objective should continue executing in detached background workers while the foreground conversation remains available for planning, decisions, and status review.
---

# Autonomous Workstream Driver

This skill consumes the kanban skill. Kanban is authoritative for intents,
tasks, links, dependencies, WIP limits, eligibility, evidence, approvals, and
closure. This skill keeps eligible work moving through a durable, detached
supervisor and recoverable worker lanes.

The supervisor enforces persisted kanban policy; it does not define, weaken, or
reinterpret WIP, eligibility, dependencies, gates, evidence, or closure. It
also does not mark a task in progress until a worker has claimed it.

## Detached Supervisor

`start background work` must register a durable run and launch a supervisor
worker independent of the foreground conversation. The foreground turn returns
after registration and initial dispatch; repeated `continue` prompts are not
required.

The supervisor remains active until the run is complete, cancelled, globally
blocked, or stopped by an autonomy or resource boundary. It wakes on worker
completion, failure, timeout, lease expiry, dependency resolution, approval,
capacity changes, and scheduled reconciliation.

The supervisor is itself a first-class worker with a lease, heartbeat,
checkpoint, authority envelope, resource limits, and restart policy. If it
dies, a later supervisor reconstructs the run from persisted state and resumes
or safely reassigns work. Never treat conversation memory or an in-process
queue as durable execution state.

## Allocation And WIP

Read current kanban state through the helper before every allocation decision.
Respect kanban WIP limits, dependency readiness, task eligibility, isolated
write ownership, approval gates, and cancellation. A completed or expired
worker lease releases capacity so the next eligible task can be pulled. A
pullable task must be a slice that an assigned worker expects to finish within
five minutes of active execution; if a task appears larger, split it before
allocating it.

A task is individually claimed with an idempotency key. Reconciliation must be
safe to repeat and must not dispatch a task twice after duplicate wake events
or supervisor restart.

The same five-minute increment boundary applies to assurance and control work.
Slice a broad review into bounded increments covering one specialist obligation,
artifact, risk area, or proof surface at a time. Each review increment records
its inspected scope, findings, evidence, remaining scope, and next action.
Heartbeat-only review activity does not extend an increment or count as review
progress.

## Worker Reuse And Context Affinity

Workers may be ephemeral or persistent specialists. Persistent specialists can
process compatible tasks serially when the task policy permits context reuse.
Reuse is an optimization, never an eligibility override.

Use explicit durable metadata before semantic similarity: shared intent or
workstream, specialist capability, repository and path scope, linked
dependencies, research topics, and produced or consumed artifacts. The task
record declares required capability, eligible worker class, preferred affinity,
context-reuse permission, isolation level, serialization requirements, expected
active duration, and the worker-visible next bounded action.

The supervisor enforces these constraints and chooses reuse, a sanitized
handoff, or a fresh worker. It retires or replaces a worker when its lease or
health is stale, authority changes, context exceeds its bound, isolation is
required, or repeated failures make reuse unsafe. Persistent workers establish
a clear task boundary, checkpoint the handoff, and do not carry unbounded or
sensitive context into the next task.

## Recovery And Blocking

Persist task allocation, worker attempt, last known status, heartbeat, lease,
checkpoint, retry history, blocker, dependency, approval, and state-transition
events in the kanban database through supported helper operations.

On restart, preserve completed tasks, expire stale leases, restore from the
latest checkpoint, retry only repeatable or idempotent actions, and reassign
eligible work. A task blocked by approval or dependency pauses its lane when
possible; independent lanes continue. Every blocked item retains an owner
lane, unblock condition, and resume priority.

Do not silently expand authority, bypass a gate, or convert a worker failure
into success. A human decision is an event that may wake affected work; silence
never grants approval.

## Worker Check-ins And Progress

Every leased worker, including the supervisor, must check in on a regular
cadence set by the run envelope. A check-in is not evidence of progress: the
worker must distinguish a liveness heartbeat from a meaningful-progress
checkpoint. The worker must also record its claim start time, because the
supervisor uses elapsed claim age to identify stalled work and to cull or
reassign slices that exceed the five-minute bound.

Each check-in records the worker and attempt identifiers; state (`working`,
`waiting`, `blocked`, `stalled`, or `complete`); heartbeat time; last
meaningful-progress time; incremental progress since the prior checkpoint;
changed artifacts, research, tests, or other observable evidence; the next
bounded action; the expected next checkpoint; and any blocker or required
input.

The supervisor pings each leased worker on the configured cadence and before
declaring a lease stale. A missed heartbeat is first marked `unknown` or
`at-risk` and pinged again before lease reclamation. A worker that responds but
reports no meaningful progress across the configured checkpoint window is
`stalled`, not healthy merely because its process is alive. Waiting and blocked
states must name the dependency, input, or approval and its resume condition.

Progress checkpoints are monotonic and idempotent: repeating a ping or
checkpoint must not create duplicate work or claim progress that cannot be
linked to an artifact, research result, test, state transition, or other
observable change. The supervisor persists the latest check-in and checkpoint
through the Kanban helper and uses their age to reclaim, retry, or reassign
work according to the envelope. It must not silently reassign a worker that is
within its heartbeat and progress windows.

## Status And Completion

Status exposes run state, supervisor heartbeat, lane state, active, waiting,
blocked, stalled, and complete workers, leases, last task status, latest
checkpoint and its age, last meaningful-progress time, queue depth, WIP
pressure, next pull candidate, and the exact reason for any pause. A status
report must not label a lane as actively progressing from an unchanged task
allocation or heartbeat alone. A queued task should remain queued until a
worker claim exists; once claimed, the worker identity and start time become
the authoritative evidence that the task is in flight.

The run is complete only when all required linked kanban tasks have accepted
evidence, reviews, and applicable gates, with no unresolved validation debt or
unaccepted residual risk. Intent realization remains a kanban decision, not a
worker claim. When a task is done, the worker should capture the durable result
in repository documentation or design notes so the corresponding kanban record
can be retained only for the project retention window and then archived once
that window expires.

## Tooling Boundary

Use the kanban helper for all database reads and writes. Never run direct SQL
from an agent or supervisor. If the helper cannot represent allocation,
leases, checkpoints, worker reuse, recovery, or status, record a tooling
improvement need and use only a documented degraded mode.

The helper/runtime must support durable run, supervisor, lane, worker attempt,
lease, heartbeat, checkpoint, progress-status, event, claim, release, retry,
pause, resume, cancel, and reconciliation operations. A persistent execution
guarantee is not valid until those operations and restart/recovery behavior are
tested.

## Quality Gate

Every lane must enforce simplicity plus idempotency plus lowest-safe error
boundary. Keep the supervisor thin: read and reconcile durable state, apply
kanban policy, dispatch bounded work, record outcomes, and recover capacity.
Do not duplicate kanban policy or hide specialist judgment in scheduling code.

Validate at minimum that worker completion backfills WIP, regular pings record
heartbeats, meaningful-progress checkpoints distinguish change from liveness,
waiting and blocked responses retain unblock conditions, stale leases are
reclaimed only after the heartbeat/progress grace window, supervisor restart
resumes work, duplicate wakeups or pings do not duplicate claims, lane-local
blockers do not halt independent lanes, approval resolution wakes the correct
lane, cancellation prevents new dispatch, work status reflects the latest
durable worker state, and all state changes use supported helper APIs.
