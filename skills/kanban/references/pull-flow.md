# Pull Flow, Capacity, And Worker Demand

Read this reference when dispatching background work, selecting the next task,
scaling workers, or handling a full downstream WIP buffer.

## Pull contract

Each stage advertises pull capacity before upstream work is admitted. A pull
request contains the stage, lane, available task slots, eligibility criteria,
required output, owner, issuance time, expiry, and idempotency key. It reserves
capacity, not a specific task. A task becomes committed only when a worker
claims it.

Pull requests are short-lived and renewable. Renewal requires a live lane and
recent meaningful progress. Expiry releases capacity without moving the task to
`Blocked` and without creating a capacity-status task event.

Choose the next task by downstream eligibility first, then critical-path or
unblock impact, then outcome advancement, then shortest estimated job, then age,
then task priority. Outcome advancement means choosing the task that most
advances an intent toward a concrete, usable, and independently verifiable user
capability. An outcome may span several bounded tasks; do not require each
individual task to be independently end-to-end. Use shortest-job-first only
among otherwise comparable tasks and apply aging so longer tasks are not
starved. Pull only work that satisfies the next stage's entry contract and has
a bounded handoff to its required output.

## WIP and worker demand

Column WIP limits are soft flow budgets: they indicate desired buffering and
parallel task flow, but do not reject task admission or prescribe worker count.
Review/validation-state WIP is independent from implementation-state WIP. A review slot may
use multiple agents when the task demand requires it; several compatible tasks
may share one persistent worker serially.

Every partitionable task declares a worker-demand contract:

- `serial`, `partitionable`, or `fan-out` parallelism;
- bounded work units with role, scope, ownership, dependencies, and output;
- minimum, target, and maximum worker demand;
- worker reuse and isolation policy;
- completion aggregation and acceptance rules.

The supervisor scales only from necessity: eligible work is waiting, existing
workers cannot meet the queue-age or service target, additional work units are
already defined, and the increase fits the task, run, host, and authority
limits. It does not scale merely because parallelism is possible.

## Backpressure

Observe pressure independently for implementation, review, validation, and
delivery. Use occupancy, overage, oldest-item age, arrival and completion rates,
worker demand, and predicted time to WIP breach. A full downstream buffer raises
the priority of completing, validating, repairing, or reviewing that state; it
does not itself reject upstream admission. Tasks retain their ordinary `Ready`,
`Active`, or `Review` state.

If downstream work is independently executable, scale its workers when pressure
shows that capacity would reduce delay. If it is waiting on an approval,
dependency, shared write, or unavailable artifact, do not scale; leave the
work in its ordinary state until the downstream condition changes. Parallel
implementation may continue past a soft downstream WIP budget when its defined
work units advance a valuable outcome and the supervisor continues to
prioritize clearing the overage.

## Completion priority

The coordinator prioritizes completing, validating, and repairing in-flight
work before pulling new backlog work. A completed slice is a scheduling event:
route its result, release or renew pull capacity, and reevaluate every affected
stage before admitting more upstream work. Refinement may prepare candidates,
but must not flood `Ready` or `Active` beyond the available pull path.

## Review independence

A reviewer may perform both assurance and control for a task when the review
criteria and evidence are task-bound, but the reviewer must not implement that
task. A reviewer may be reused across tasks serially with a fresh task-scoped
briefing. Use a fresh worker identity whenever implementation ownership,
specialist authority, artifact isolation, or required independence changes.
