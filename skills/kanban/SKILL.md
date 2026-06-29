---
name: kanban
description: Use when planning, prioritizing, maintaining project kanban state, walking the board, grooming backlog, persisting plans or theme principles, reporting work status, selecting next tasks by review-first and WSJF discipline, or coordinating delegated/background/parallel work as kanban lanes with WIP limits, backfill goals, readiness gates, explicit validation, and closure proof.
---

# Kanban

## Use This Skill When

Use this skill for project planning, backlog grooming, work status, next-task selection, board walks, and delegated/background execution. This is the canonical skill for both planning and worker coordination.

Read the reference that matches the request:

- `references/board-walk.md`: when the user says `walk the board`, asks for status/progress, asks what to start next, or asks to backfill Ready/Active work.
- `references/delegation.md`: when the user asks for async, background, delegated, queued, autonomous, or parallel work.

## Board State

Use `.kanban/kanban.db` as the canonical project-local state. It stores cards, backlog records, clarifications, theme principles, columns, transitions, WIP limits, backfill goals, validation state, and events.

Do not use legacy `.kanban/kanban.yaml` or `.kanban/backlog.yaml` files for import, export, review snapshots, or ongoing state. The SQLite database and helper commands are the only machine-editable board state.

If no project kanban state exists, keep planning in-session unless the user asks to persist a board or backlog. When persistence is requested, initialize `.kanban/kanban.db` with the bundled helper.

## Helper

Use the bundled helper from this skill:

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" status
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" validate
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" column list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" column transition list
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task list --column Ready
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task show <task-id>
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" task move <task-id> Active --owner <owner>
```

Supported command groups:

```text
init
status
validate
config list/set
column list/add/transition
task list/show/move/validation
backlog list/add
clarify add/list
principle add/list
```

Prefer the helper for all machine updates so changes are record-scoped and validated.

## Columns And Policy

Respect project-declared columns, positions, required rules, transitions, WIP limits, and backfill goals. Do not assume a fixed workflow when `.kanban/kanban.db` exists.

The default seeded workflow is:

- `Backlog`: known work not ready to pull.
- `Ready`: clear, unblocked work with owner/scope/exit criteria.
- `Active`: work currently being executed.
- `Blocked`: work waiting on a named unblock condition.
- `Review`: completed output waiting for acceptance or validation review.
- `Done`: accepted work with proof.
- `Deferred`: intentionally postponed work with a resume condition.

Move cards only through declared transitions. If a project needs a bespoke workflow state, add a column and explicit transitions with promotion rules rather than forcing a card into an undeclared state.

Configure column-scoped limits and goals with:

```sh
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config set wip_limit -C Active -L 4
python3 "$CODEX_HOME/skills/kanban/scripts/kanban.py" config set backfill_goal -C Ready -T 10
```

Treat WIP limits as hard caps. Treat backfill goals as targets that still yield to readiness, ownership conflicts, validation risk, and user priorities.

## Card Rules

Keep cards compact and concrete:

- `id`: stable short name.
- `themes`: stable progress grouping slugs.
- `column`: current board column.
- `owner`: person, agent, worker, or `unassigned`.
- `scope`: files, systems, or decision area.
- `goal`: one outcome.
- `dependencies`: upstream cards, approvals, artifacts, or external state.
- `pull_criteria`: what must be true before Active.
- `exit_criteria`: deliverable and acceptance conditions.
- `validation`: required proof, expected evidence, and status.
- `blocker`: blocker owner and unblock condition, or `none`.
- `priority`: why this card is next.
- `value`, `effort`, `wsjf`: optional priority estimates.
- `complexity`, `ambiguity`, `review_rigor`: explicit estimates when useful.
- `plan`: persisted plan context for discussable work.
- `readiness`: confidence plus readiness for scope, success criteria, constraints, and implementation plan.

Implementation cards must not enter `Active` until confidence and readiness are at least 99% for scope, success criteria, operational constraints/requirements, and implementation plan, with the plan confirmed. Planning, research, clarification, and validation-design cards may run below that threshold when their purpose is to raise readiness.

## Priority Discipline

Use this pull order for recommendations and autonomous coordination:

1. Close `Review` items that can be accepted or returned with bounded follow-up.
2. Advance already-started `Active` items.
3. Clear blockers when doing so unblocks reviewable or active work.
4. Pull from `Ready`.
5. Promote or start new backlog work only after earlier classes are exhausted, blocked, or intentionally deferred.

Within the same pull class, use weighted shortest job first: prefer the highest value output per unit effort cost. Estimate value from user-visible benefit, risk reduction, dependency unblock value, validation debt reduction, and theme progress. Estimate effort from file scope, complexity, validation cost, coordination cost, and uncertainty.

## Themes And Principles

Tag cards and backlog records with one or more stable lowercase themes when possible. Themes track area progress; columns track flow state.

Record user-stated general rules as theme principles in the project kanban database. A principle under one theme can govern cards in other themes when its scope says it applies. Before planning, dispatching, or accepting work, check relevant principles and identify suspected violations, needed exceptions, or corrective backlog items.

## Status Shape

For status reports, group by column and include only useful fields:

```text
Ready
- <id>: <goal> | owner: <owner> | next: <pull condition or first action>

Blocked
- <id>: <goal> | blocked by: <owner/condition> | resume: <condition>

Review
- <id>: <goal> | proof: <evidence> | needed: <acceptance check>
```

End with the next pullable card, highest-risk blocker, validation debt, and concise WSJF rationale when recommending work.
