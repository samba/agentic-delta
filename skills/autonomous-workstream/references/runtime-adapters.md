# Runtime Adapter Contract

Use this reference when the selected agent platform provides native detached
jobs, background sessions, remote coding agents, or an API for launching and
monitoring them.

## Boundary

The runtime adapter owns platform-specific job lifecycle. Kanban remains the
source of truth for task eligibility, state, WIP, leases, claims, evidence,
review independence, and completion. A runtime job is an execution mechanism,
not a replacement for a task or a durable run record.

Prefer the native detached capability when it supports the required contract.
If it does not, use an ordinary live worker lane. Do not invent a persistent
server abstraction from a platform that only promises a bounded job or session.

## Minimum adapter operations

An adapter should provide the closest available equivalent of:

```text
submit(task, briefing, environment) -> job
status(job) -> state, progress, outputs, failure
follow_up(job, message) -> acknowledgement
cancel(job) -> acknowledgement
collect_artifacts(job) -> artifacts
release(job) -> cleanup result
```

The adapter must expose or document:

- job and task identity;
- repository, branch, worktree, or workspace identity;
- isolation boundary and network access;
- maximum execution lifetime and timeout behavior;
- whether follow-up messages are supported;
- cancellation and cleanup semantics;
- artifact, commit, branch, or pull-request handoff;
- status and failure states;
- whether background processes survive only the current job.

## Dispatch sequence

1. Pull and claim the task through Kanban, consuming a lease when required.
2. Build the live briefing from current task state, criteria, evidence,
   revision, authority limits, model tier, bounded next action, and expected
   checkpoint.
3. Submit exactly the claimed task to the adapter, preserving task and lease
   identity in the job metadata or prompt.
4. Monitor status and follow up only within the task’s authority and bounded
   objective.
5. Collect artifacts and meaningful results before recording task events or
   moving state.
6. On success, failure, cancellation, or timeout, release the job and renew or
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

If adapter status is unavailable, the job times out, or the runtime disappears,
stop dispatching through its lease and follow the coordination protocol. Do not
mark the task complete from a missing or partial response. Inspect repository
state and durable task evidence, record the recovery decision, and issue a
fresh briefing before resuming or reassigning.
