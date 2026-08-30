---
name: kanban
description: Use when planning, prioritizing, maintaining project kanban state, reporting work status, walking the board, mapping workstreams, preparing next work, refining backlog, reviewing or closing completed work, or coordinating background work with WIP limits, readiness gates, validation, and closure proof.
---

# Kanban

## Use This Skill When

Use this skill for project planning, intent refinement, work-item status, next-task selection, board walks, workstream mapping, viable autonomous execution, and background worker coordination. This is the canonical skill for both planning and worker coordination.

## Human Objectives And Work Items

Use `intent` as the human-facing term for an early-stage objective that may be an idea, problem, concern, opportunity, or question. Interpret those words naturally as the intent's `kind`; do not create separate workflows for each synonym.

An intent is not an executable work item. Its lifecycle is `captured`, `researching`, `refining`, `planned`, `deferred`, or `closed`. A closed intent has exactly one closure reason: `realized` or `rejected`. `Done` applies only to accepted work items.

Work items move through the board workflow: `Backlog`, `Ready`, `Active`, `Blocked`, `Review`, `Done`, or `Deferred`. Every work item must link to one or more intents before entering `Ready`; an intent may link to many work items. Agent/session assignment is internal coordination metadata and should not be presented as human ownership unless requested.

Research is a first-class path: capture the intent, delegate bounded research, retain findings and references, discuss and refine the result, agree a plan, create linked work items, then implement and validate them. An intent becomes `realized` only when its required linked work is accepted.

Read `references/intents-and-migration.md` when creating, researching, migrating, or reporting intents, links, historical references, or legacy structures.

Read the reference that matches the request:

- `references/commands.md`: first, for exact workflow command routing, canonical command behavior, and deprecated command warnings.
- `references/board-walk.md`: when the user says `walk board`, `work status`, `review completed work`, `close completed work`, `refine backlog`, `prepare next work`, asks for status/progress, asks what to start next, or asks to backfill Ready/Active work.
- `references/backlog-refinement.md`: when the user asks to refine, split, clarify, decompose, groom, or make candidate work easier to execute.
- `references/intents-and-migration.md`: when handling the intent lifecycle, legacy migration, or research-reference recovery.
- `references/delegation.md`: when the user says `start background work`, `run workstream`, `pause background work`, `resume background work`, `stop background work`, or otherwise asks for background, queued, autonomous, or parallel work.
- `references/autonomous-loop.md`: when defining, running, reviewing, or repairing an autonomous software-development loop with goal intake, research, design validation, implementation, verification, review, and rework routing.
- `references/validation-contracts.md`: when planning, delegating, executing, or reviewing independent validation of agent work, background tasks, implementation claims, research outputs, commits, skill changes, data pipelines, or closure proof.

## Board State

Use `.kanban/kanban.db` as the canonical project-local state. It stores intents, work items, intent links, research references, clarifications, theme principles, columns, transitions, WIP limits, backfill goals, validation state, and events.

Do not write YAML for kanban state, backlog output, queue output, exports, review snapshots, or ongoing state. The SQLite database and helper commands are the only machine-editable board state.

Agents must not run direct SQL against the kanban database, including ad hoc
read-only queries. Use the bundled helper for every board read and mutation so
the schema, compatibility rules, and audit behavior remain centralized. If the
helper lacks a needed capability, stop the dependent operation and raise a
tooling-improvement request to the user describing the required command/API,
the information or mutation it must support, and its acceptance criteria. Do
not bypass the gap with SQL, alternate database clients, or one-off scripts.

Legacy `.kanban/kanban.yaml`, `.kanban/backlog.yaml`, or similar YAML files may be read only for one-way migration into `.kanban/kanban.db`. After migration, continue from SQLite and leave legacy YAML files untouched unless the user explicitly asks to archive or remove them.

If no project kanban state exists, keep planning in-session unless the user asks to persist a board or backlog. When persistence is requested, initialize `.kanban/kanban.db` with the bundled helper.

## Helper

Use the bundled helper from this skill:

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" init
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" legacy-import .kanban/kanban.yaml --kind tasks
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" legacy-import .kanban/backlog.yaml --kind backlog
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" status
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" validate
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" column list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" column transition list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task list --column Ready
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task show <task-id>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task move <task-id> Active --owner <owner>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task blocker add <task-id> <blocked-by> --reason "<why>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task review accept <task-id> --evidence "<proof>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog dependency add <idea-id> <dependency-id>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog priority set <idea-id> --value 10 --reason "<why before other work>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog status <idea-id> done --reason "<completion evidence>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog update <idea-id> --summary "<revised summary>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" intent add <intent-id> "<summary>" --kind concern
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" intent status <intent-id> researching
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" intent link <intent-id> <task-id>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" reference add <reference-id> <url> --topic <topic>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" migrate references
python3 "$CODEX_HOME/skills/kanban/scripts/validation_contract.py" --target "<artifact or claim>" --probe "<command or check>" --pass-criterion "<what proves acceptance>"
```

Supported command groups:

```text
init
legacy-import
status
validate
config list/set
column list/add/transition
task list/show/move/validation
task blocker add/remove
task review start/accept/rework
task event add
task metadata add/remove
task dependency add/remove/list
task priority set/bump
backlog list/add/show/status/update
backlog dependency add/remove/list
backlog priority set/bump
intent add/list/show/status/work/link/unlink
reference add/list/link
migrate references
clarify add/list
principle add/list
```

Use the helper for all machine reads and updates so operations are record-scoped,
validated, and auditable. Do not update or query `.kanban/kanban.db` with direct
SQL for any workflow purpose; add or improve a helper command instead.
Use helper verbs such as `add` and `remove` for blockers, dependencies, and metadata instead of editing SQLite directly. Avoid ambiguous words such as `clear` in user-facing workflow commands; remove a specific blocker or metadata key instead.

## Columns And Policy

Respect project-declared columns, positions, required rules, transitions, WIP limits, and backfill goals. Do not assume a fixed workflow when `.kanban/kanban.db` exists.

The default seeded workflow is:

- `Backlog`: known work items not ready to pull. Do not use this label for the intent registry.
- `Ready`: clear, unblocked work with scope/exit criteria/validation and at least one intent link.
- `Active`: work currently being executed.
- `Blocked`: work waiting on a named unblock condition.
- `Review`: completed output waiting for acceptance or validation review.
- `Done`: accepted work with proof.
- `Deferred`: intentionally postponed work with a resume condition.

Move cards only through declared transitions. If a project needs a bespoke workflow state, add a column and explicit transitions with movement rules rather than forcing a card into an undeclared state.

Configure column-scoped limits and goals with:

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config set wip_limit -C Active -L 4
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config set backfill_goal -C Ready -T 10
```

Treat WIP limits as hard caps. Treat backfill goals as targets that still yield to readiness, ownership conflicts, validation risk, and user priorities.

## Work-Item Rules

Keep cards compact and concrete:

- `id`: stable short name.
- `themes`: stable progress grouping slugs.
- `column`: current board column.
- `worker_assignment`: internal worker/session metadata; omit from ordinary human-facing reports.
- `scope`: files, systems, or decision area.
- `goal`: one outcome.
- `intent_links`: one or more supporting intents.
- `dependencies`: upstream work items, approvals, artifacts, or external state.
- `pull_criteria`: what must be true before Active.
- `exit_criteria`: deliverable and acceptance conditions.
- `validation`: required proof, expected evidence, and status.
- `blocker`: blocker owner and unblock condition, or `none`.
- `priority`: why this card is next.
- `value`, `effort`, `wsjf`: optional priority estimates.
- `complexity`, `ambiguity`, `review_rigor`: explicit estimates when useful.
- `plan`: persisted plan context for discussable work.
- `readiness`: confidence plus readiness for scope, success criteria, constraints, and implementation plan.

Implementation cards must not enter `Active` until confidence and readiness are at least 99% for scope, success criteria, operational constraints/requirements, implementation plan, and design-validation status, with the plan confirmed. Planning, research, clarification, design-draft, and validation-design cards may run below that threshold when their purpose is to raise readiness.

## Research-First Gates

Front-load research before design or implementation when a change involves sensitive design choices, operational risk, security hazards, privacy controls, or performance-critical tradeoffs. Research should happen early enough to shape the design, not after implementation has created rework pressure.

Create an explicit research or design card before implementation when work includes any of:

- network isolation, VPN, DNS, identity, secrets, credential rotation, backup/restore, or access-control boundaries;
- production operations, destructive actions, data movement, migrations, failover, disaster recovery, or rollback behavior;
- privacy-preserving controls, traffic routing, telemetry/logging exposure, or compliance-sensitive behavior;
- performance, scalability, storage, scheduling, or reliability choices where multiple architecture patterns are plausible;
- new infrastructure primitives whose failure modes are not already proven in this project.

Research cards should identify authoritative sources, candidate patterns, failure modes, validation implications, and the recommended contract. Their completion evidence must persist the findings, the conclusion, and the design/implementation choices that follow from it, so downstream cards can cite concrete evidence instead of repeating the research. Downstream planning must depend on that research when its answer materially affects scope or safety.

## Background Refinement

Every `walk board`, `run workstream`, and `prepare next work` pass includes a backlog refinement check.
Treat refinement as background work once Review/Active/WIP discipline is
honored: map unclear integration paths, inspect current code and contracts,
perform needful research when local context is insufficient, compare concrete
implementation options, and persist decisions for human review before downstream
implementation assumes them.

Refinement must document:

- the selected data/control path across components;
- rejected or deferred alternatives and why they were not selected;
- assumptions that need later validation;
- exact files, interfaces, and runtime handoff points involved;
- follow-on implementation and validation tasks created or revised; and
- a short decision summary suitable for the human to review and redirect.

## Validation Contracts

Use kanban validation contracts when validation must be independent, explicit,
and reviewable. This is part of flow control: a card should not move to `Done`
or be accepted from `Review` until the required validation evidence is present.

Before delegating or accepting validation, define:

- target artifact, behavior, claim, or card;
- allowed scope and prohibited scope;
- expected evidence;
- pass/fail criteria;
- commands, probes, manifests, database queries, screenshots, source links, or diff checks to run;
- risks the validator should try to disprove;
- final report shape and reviewer handoff.

Keep implementation and validation separate. Validators should not silently fix
the work unless asked; they should inspect the output, attempt to disprove the
claim with concrete probes, and report `pass`, `fail`, or `partial` with
evidence and residual risk.

## Priority Discipline

Use this pull order for recommendations and autonomous coordination:

1. Close `Review` items that can be accepted or returned with bounded follow-up.
2. Advance already-started `Active` items.
3. Clear blockers when doing so unblocks reviewable or active work.
4. Pull from `Ready`.
5. Refine or start new backlog work only after earlier classes are exhausted, blocked, or intentionally deferred.

Within the same pull class, use weighted shortest job first: prefer the highest value output per unit effort cost. Estimate value from user-visible benefit, risk reduction, dependency unblock value, validation debt reduction, and theme progress. Estimate effort from file scope, complexity, validation cost, coordination cost, and uncertainty.

## Themes And Principles

Tag intents and work items with one or more stable lowercase themes when possible. Themes track area progress; intent state and work-item columns track flow state.

Record user-stated general rules as theme principles in the project kanban database. A principle under one theme can govern cards in other themes when its scope says it applies. Before planning, dispatching, or accepting work, check relevant principles and identify suspected violations, needed exceptions, or corrective backlog items.

## Status Shape

For status reports, group by column and include only useful fields:

```text
Ready
- <id>: <goal> | next: <pull condition or first action>

Blocked
- <id>: <goal> | blocked by: <condition> | resume: <condition>

Review
- <id>: <goal> | proof: <evidence> | needed: <acceptance check>
```

End with the next pullable card, highest-risk blocker, validation debt, and concise WSJF rationale when recommending work.

## Intent Decisions

Use the intent lifecycle for human objective decisions. Legacy `backlog` commands may remain compatibility aliases during migration, but their output must be labeled as intents.

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog status <idea-id> done --reason "<what completed>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog status <idea-id> rejected --reason "<why rejected>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog status <idea-id> deferred --reason "<resume condition or deferral reason>"
```

Allowed intent states are `captured`, `researching`, `refining`, `planned`, `deferred`, and `closed`. A closed intent requires `closure=realized` or `closure=rejected`; preserve the historical reason and never silently classify an ambiguous legacy terminal record.

Use `backlog update` to revise an idea summary or add notes without changing
status:

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog update <idea-id> --summary "<new summary>"
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" backlog update <idea-id> --note "<decision context>"
```
