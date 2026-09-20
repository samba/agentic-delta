# Kanban Helper Commands

The helper owns durable Kanban state. Worker sessions, heartbeats, and run
history remain in the live autonomous-workstream runtime.

All commands use:

```bash
python3 skills/kanban/scripts/kanban.py --db .kanban/kanban.db <command>
```

## Intents

```bash
intent add <id> <summary> --type feature|use-case|capability|problem
intent list
intent show <id>
intent status <id> <captured|researching|refining|planned|deferred|closed>
```

`intent add` accepts an extensible type. A task may link to multiple intents.
`goal capture` remains a concise capture alias for conversational workflows.

## Tasks

Customize the project state sequence with:

```bash
state list
state add <id> <name> --position <n> [--previous <state-id>] [--next <state-id>] \
  [--wip-limit <n>] [--required-fields '<json-array>'] \
  [--assurance-on-entry] [--worker-entry] [--review-queue] \
  [--requires-checks] [--requires-evidence] \
  [--requires-reviewed-references] [--terminal]
```

States are process steps, not aliases for the default names. Their display
names may be arbitrary. Policy flags define what happens at that step; the
predecessor and successor define the linear process sequence. The default
five-state workflow is only seed configuration.

```bash
task add <id> <summary> --intent <intent-id> [--intent <intent-id> ...]
task list [--state <state>] [--type <task-type>]
task show <id>
task refine <id> [--scope <scope>] [--owner <owner>] \
  [--acceptance <criterion>] [--validation <criterion>] \
  [--details '<json-object>'] [--actor <identity>]
task purge <id> --confirm
task move <id> <state-id-or-name>
task claim <id> --actor <worker>
task assign <id> <owner> [--actor <identity>]
task requeue <id> [--state <state-id-or-name>] --reason <reason> [--actor <identity>]
task event add <task-id> <event-type> <summary> [--actor <identity>] \
  [--payload '<json-object>'] [--idempotency-key <key>]
task event list <task-id> [--json]
task dependency add <task-id> <dependency-id>
task dependency remove <task-id> <dependency-id>
```

`task claim` atomically claims a task whose successor is configured as a
worker-entry state, validates that successor's requirements, moves the task
there, and records a claim event. If the task is already in a `review_queue`
state, it records a review claim without moving the task or changing its
implementation owner. It does not bind a capacity lease to the task.

`task refine` updates scope, owner, acceptance criteria, validation criteria,
or task details and records a refinement event. `task assign` changes the
implementation owner and records an assignment event; it requires a concrete
owner. `task requeue` moves recoverable work to its predecessor (or an
explicit state), records the recovery reason, and preserves truthful task
history; it is not a blocked state.

Before refining a task into `Ready`, review and link relevant research
references, identify an existing pattern to adopt or extend, and record the
selection and rationale in the task details. If no suitable pattern exists,
record that conclusion and its supporting evidence.

When reusable software may apply, investigate open-source library candidates
before proposing bespoke implementation. Compare capability fit, compatibility,
integration cost, license, provenance, security, and replacement risk, then
record the selected library and rationale—or why none is suitable—in the task
details.

`task purge` permanently removes the task. Before using it, confirm that the
task is terminal, required checks and evidence are complete, task events have
been reviewed, and no follow-up, validation debt, or residual-risk decision
still depends on it. Its events, checks, evidence, intent/reference links,
capacity reservations, and dependency edges are cascaded; linked intents,
research references, and specialist roles remain.

```bash
pull next [--claim --actor <worker>] [--lease <lease-id>] [--json]
```

`pull next --lease` selects and claims work while consuming one lease slot in
the same transaction. Without a lease, it selects the oldest highest-priority
task whose next state is a configured worker-entry state, or an existing
`review_queue` task, and whose dependencies are terminal. With `--claim`,
selection and claim are one transaction. A review claim keeps the task in its
review state and preserves implementation ownership.

Use `--type bug` for defect work. Backlog candidates are ordinary tasks in the
Backlog state.

Worker demand is stored on the task:

```bash
task demand set <task-id> \
  --parallelism serial|partitionable|fan-out \
  --min-workers <n> --target-workers <n> --max-workers <n> \
  --work-units '<json-array>' --reuse-policy <policy> \
  --isolation <boundary> --aggregation <rule>
```

## Review and evidence

```bash
review check add <check-id> <task-id> assurance|control <criterion> \
  [--role <specialist-role-id>] [--optional]
review check record <check-id> <task-id> passed|failed|not_applicable \
  --reviewer-role <specialist-role-id> --reviewer-worker-id <worker> \
  [--finding <text>] [--rationale <text>]
review check list <task-id>

evidence add <evidence-id> <task-id> <artifact> \
  --result <result> --producer <identity> [--check-id <check-id>] \
  [--revision <revision>] [--probe <probe>] [--location <location>]
evidence list <task-id> [--json]
```

When a task enters a state whose policy requires assurance, every active
specialist role is enlisted in a required assurance check. The database
enforces state policy, reviewer independence, and terminal check/evidence
requirements.

## Specialists and guidance

```bash
specialist add <id> <name> <purpose> <description>
specialist list

guidance add <id> <statement> --version <n> [--type principle|tenet]
guidance reference <guidance-id> <reference-id> --version <n>
```

Guidance is versioned in one table. It may cite research references.

## Research references

```bash
reference add <id> <url> [--title <title>] [--publisher <publisher>]
reference link <reference-id> --intent-id <intent-id>
reference link <reference-id> --task-id <task-id>
reference review <reference-id> reviewed|rejected|unreviewed
```

Design work should gather and review sources before finalizing task scope or
guidance.

## Pull capacity

```bash
pull next [--claim --actor <identity>] [--lease <lease-id>] [--json]
task claim <task-id> --actor <identity>

pull lease issue <lease-id> --stage <stage> --lane <lane> --slots <n> \
  --eligibility '<json-object>' --required-output <contract> \
  --owner <identity> --ttl-seconds <n> --idempotency-key <key>
pull lease renew <lease-id> --ttl-seconds <n>
pull lease release <lease-id>
pull lease reserve <lease-id> <task-id> [--slots <n>]
pull lease release-reservation <lease-id> <task-id>
```

`pull next --lease` selects and claims work while consuming one lease slot in
the same transaction. Without a lease, `pull next` selects dependency-free
work by eligibility, explicit task priority, age, and stable ID order. Review
workers must assemble a fresh task-scoped brief from current state, checks,
evidence, revision, and events; an implementation plan is context only, never
acceptance proof.
Claiming is compare-and-set inside a transaction. Leases reserve capacity
rather than worker runs; reservations consume slots atomically. Expiry
releases capacity without moving work to Blocked. A supervisor may derive a
critical-path priority and write it to the task before pulling; the helper does
not calculate graph centrality itself.

## Status and validation

```bash
status
status --json
validate
```

`status --json` is the preferred input for a supervisor scheduling pass.
