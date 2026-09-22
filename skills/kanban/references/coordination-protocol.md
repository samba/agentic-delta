# Coordination Protocol

This reference defines live coordination between the supervisor and workers.
It is intentionally ephemeral: Kanban persists meaningful task events, checks,
evidence, and pull-capacity leases; it does not persist runs, attempts,
heartbeats, or chat transcripts.

## Authority boundary

The supervisor is coordinator-only. It may select, dispatch, poll, renew,
requeue, recover, and report, but it must not claim implementation work,
manufacture worker checkpoints, or present its administrative events as worker
progress. A worker must acknowledge its task and lease, complete the capability
preflight, and emit the first live checkpoint through the runtime channel
before it claims `Active` or reports implementation progress. Until then, the
task remains `Ready`.

Worker identity, liveness, start time, checkpoint age, fencing, and replacement
idempotence belong to the live runtime adapter and supervisor memory. They must
not be added as Kanban tables or simulated with durable task events. If a live
worker acknowledgement cannot be obtained, leave work in `Ready` and report
the dispatch failure.

The first checkpoint is a worker-originated handshake, not a Kanban event: it
must identify the verified runtime worker, task and lease, start time, bounded
next action, workspace identity, and environment result. Only that worker may then invoke the
helper claim using its verified worker ID as actor. A supervisor owner,
synthetic recovery owner, submission ID, administrative rebrief, or state
transition never qualifies as worker provenance.

Maintain one live assignment for each serial task. Do not dispatch a second
worker or reassign a task until the prior worker is fenced through the runtime
adapter. Requeue and replacement decisions must be idempotent in supervisor
memory, so repeated wakes cannot create competing workers.

## Progress messages

Send compact deltas, not repeated briefings or full transcripts. A progress
message names the task, current state, observed change, artifact or evidence
reference, blocker (or `none`), and one bounded next action. A heartbeat may say
only that the worker is alive; it is not progress or acceptance evidence.

## Lease renewal and freshness

The supervisor renews a capacity lease before its TTL expires and records an
acknowledgement in the live worker channel. The worker acknowledges the current
assignment and lease identity; acknowledgement does not extend a lease by
itself. Freshness requires both a responsive worker and recent meaningful
progress or a named waiting/blocking condition. Do not infer freshness from a
process or unchanged heartbeat alone.

Each assignment has one bounded next action and an expected checkpoint. A
worker is fresh when it is responsive and either reports meaningful progress,
reports a named waiting or blocking condition, or is still within the expected
checkpoint window. Heartbeats alone never extend productive progress.

## Timeout

If renewal acknowledgement or worker response is missing until the lease
expires, stop dispatching through that lease and let its reservation release.
Expiry does not move the task to `Blocked` and does not authorize silent
reassignment. If the worker is responsive but produces no observable progress
across the configured checkpoint window, classify the lane as stalled and
escalate for recovery; do not fabricate success.

Administrative claims, rebriefs, requeues, and recovery decisions do not reset
worker progress age. Staleness uses the last meaningful worker checkpoint held
by the live supervisor, not task `updated_at`.

## Recovery

On wake or restart, inspect current task state, owner, dependencies, latest
meaningful events, checks, evidence, and filesystem/version-control state.
Reconcile live adapter workers, fence any stale worker before replacement, then
choose resume, rework, review, or reassignment. Record the meaningful decision
as a task event, stop using the stale lease, and issue a fresh briefing. “Fence”
means that the stale runtime worker cannot dispatch more work; it does not
require a fencing table. Recovery is idempotent in the live supervisor, not in
persisted run history. Never depend on a removed run record or replay an old
chat transcript.
Independent lanes may continue while one lane waits for authority, a
dependency, or recovery.

If a task has a confirmed external-capability blocker, leave it in `Ready` and
hold a live scheduler suppression keyed to the blocker and environment fingerprint.
Re-test before clearing it; do not treat suppression as a blocked
Kanban state or repeatedly pull the same unavailable task.

Each fresh briefing states the task and lease IDs, repository/path scope,
objective, acceptance and validation criteria, current revision, required
output, permitted tools, prohibited side effects, approval boundaries, stop
conditions, model/reasoning tier, bounded next action, and expected checkpoint.

When a review lane pulls a task already in a `review_queue` state, claim the
review without moving the task or replacing its implementation owner. Assemble
a fresh task-scoped review brief from the current revision, acceptance and
validation criteria, all required checks, all evidence, and recent task events.
An old implementation plan is context only; it is never evidence that the
current revision is correct or that review requirements were satisfied. Report
review-worker liveness separately from completed checks, evidence, and the
review handoff; ownership alone is not review progress.
