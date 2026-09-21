# Runtime Adapter Contract

Use this reference when the selected agent platform provides native detached
jobs, background sessions, remote coding agents, or an API for launching and
monitoring them.

## Boundary

The runtime adapter owns platform-specific supervisor and worker lifecycle.
Kanban remains the source of truth for task eligibility, state, WIP, leases,
claims, evidence, review independence, and completion. Runtime identities,
liveness, checkpoints, fencing, retry counts, and dispatch assignments remain
live adapter/supervisor state; they are not replacement tables or durable run
records.

Prefer the native detached capability when it supports the required contract.
If it does not, use an ordinary live worker lane. Do not invent a persistent
server abstraction from a platform that only promises a bounded job or session.

## Minimum adapter operations

An adapter should provide the closest available equivalent of:

```text
start_supervisor(objective, environment) -> supervisor_id
status_supervisor(supervisor_id) -> live/dead, next_wake, failure
submit_worker(supervisor_id, task, briefing, environment) -> worker_id
acknowledge_worker(worker_id, task, lease) -> acknowledgement
status_worker(worker_id) -> state, progress, outputs, failure
follow_up(worker_id, message) -> acknowledgement
cancel_worker(worker_id) -> acknowledgement
collect_artifacts(worker_id) -> artifacts
release_worker(worker_id) -> cleanup result
```

The adapter must expose or document:

- supervisor, worker, and task identity;
- the worker acknowledgement and task/lease binding;
- repository, branch, worktree, or workspace identity;
- isolation boundary and network access;
- maximum execution lifetime and timeout behavior;
- whether follow-up messages are supported;
- cancellation and cleanup semantics;
- artifact, commit, branch, or pull-request handoff;
- status and failure states;
- whether background processes survive only the current job.

If the adapter cannot verify a live supervisor identity, autonomous continuation
is unavailable. Run the loop in the foreground and report that fact explicitly.

## Dispatch sequence

1. Start or verify exactly one supervisor and retain its live identity.
2. Pull or select the task through Kanban, consuming a lease when required.
3. Build the live briefing from current task state, criteria, evidence,
   revision, authority limits, model tier, bounded next action, and expected
   checkpoint.
4. Submit exactly one worker for the task, preserving task and lease identity
   in the job metadata or prompt, then verify the live worker identity.
5. Require the worker to acknowledge the task and lease and claim the task
   through Kanban. The supervisor must not claim implementation or emit worker
   checkpoints on the worker's behalf.
6. Monitor status and follow up only within the task’s authority and bounded
   objective.
7. Collect artifacts and meaningful results before recording task events or
   moving state.
8. On success, failure, cancellation, or timeout, release the worker and renew or
   release Kanban capacity according to the live recovery protocol.

Do not dispatch the same claim to multiple runtime jobs unless the task’s
worker-demand contract explicitly defines independent work units. A runtime
platform’s ability to start more jobs is not evidence that scaling is needed.

## Environment and server processes

Treat remote environments as ephemeral unless the adapter explicitly guarantees
retention. A startup command or background terminal may support tests, a local
service, or a watcher during one job, but it does not establish a durable
project server. Record the service endpoint and lifetime in the live briefing
when a worker depends on one; stop or release it with the job.

## Recovery

If adapter status is unavailable, the worker times out, or the runtime
disappears, stop dispatching through its lease and follow the coordination
protocol. Fence the live worker through the adapter before replacement. Do not
mark the task complete from a missing or partial response. Inspect repository
state and durable task evidence, record only the meaningful recovery decision,
and issue a fresh briefing before resuming or reassigning. Recovery identity,
staleness, and replacement idempotence remain live runtime concerns.
