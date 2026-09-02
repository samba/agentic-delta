---
name: autonomous-workstream
description: Use when a well-defined kanban objective should continue executing in detached background workers while the foreground conversation remains available for planning, decisions, and status review.
---

# Autonomous Workstream Driver

This skill consumes the kanban skill. Kanban is authoritative for intents,
tasks, links, dependencies, WIP limits, eligibility, evidence, approvals, and
closure. This skill keeps eligible work moving through a durable, detached
supervisor and recoverable worker lanes.

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
worker lease releases capacity so the next eligible task can be pulled.

A task is individually claimed with an idempotency key. Reconciliation must be
safe to repeat and must not dispatch a task twice after duplicate wake events
or supervisor restart.

## Worker Reuse And Context Affinity

Workers may be ephemeral or persistent specialists. Persistent specialists can
process compatible tasks serially when the task policy permits context reuse.
Reuse is an optimization, never an eligibility override.

Use explicit durable metadata before semantic similarity: shared intent or
workstream, specialist capability, repository and path scope, linked
dependencies, research topics, and produced or consumed artifacts. The task
record declares required capability, eligible worker class, preferred affinity,
context-reuse permission, isolation level, and serialization requirements.

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

## Status And Completion

Status exposes run state, supervisor heartbeat, lane state, active and waiting
workers, leases, last task status, checkpoints, queue depth, WIP pressure, next
pull candidate, and the exact reason for any pause.

The run is complete only when all required linked kanban tasks have accepted
evidence, reviews, and applicable gates, with no unresolved validation debt or
unaccepted residual risk. Intent realization remains a kanban decision, not a
worker claim.

## Tooling Boundary

Use the kanban helper for all database reads and writes. Never run direct SQL
from an agent or supervisor. If the helper cannot represent allocation,
leases, checkpoints, worker reuse, recovery, or status, record a tooling
improvement need and use only a documented degraded mode.

The helper/runtime must support durable run, supervisor, lane, worker attempt,
lease, heartbeat, checkpoint, event, claim, release, retry, pause, resume,
cancel, and reconciliation operations. A persistent execution guarantee is
not valid until those operations and restart/recovery behavior are tested.

## Quality Gate

Every lane must enforce simplicity plus idempotency plus lowest-safe error
boundary. Keep the supervisor thin: read and reconcile durable state, apply
kanban policy, dispatch bounded work, record outcomes, and recover capacity.
Do not duplicate kanban policy or hide specialist judgment in scheduling code.

Validate at minimum that worker completion backfills WIP, stale leases are
reclaimed, supervisor restart resumes work, duplicate wakeups do not duplicate
claims, lane-local blockers do not halt independent lanes, approval resolution
wakes the correct lane, cancellation prevents new dispatch, and all state
changes use supported helper APIs.
