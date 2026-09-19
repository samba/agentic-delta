---
name: kanban
description: Use when capturing intents, refining and prioritizing tasks, maintaining project state, coordinating pull-based work, or recording assurance, control, research, guidance, and evidence.
---

# Kanban Coordinator

Kanban is the durable work-state kernel for the project. It records intents,
tasks, customizable task states, dependencies, research inputs, assurance and
control checks, evidence, guidance, task events, and short-lived pull capacity.
It does not persist worker runs or attempt histories.

Use `scripts/kanban.py` for all Kanban state changes. Do not edit the SQLite
database directly. The autonomous-workstream skill owns live worker sessions,
worker reuse, scheduling, queue draining, and recovery decisions.

## Durable model

An intent is an objective or problem, classified by an extensible type such as
`feature`, `use-case`, `capability`, or `problem`. A task is actionable work;
bugs are tasks with `task_type=bug`. Tasks may serve multiple intents through
`task_intents`.

Every task has a foreign-key `state_id` into the project’s `task_states` table.
The default linear states are:

```text
Backlog → Ready → Active → Review → Done
```

Projects may add or customize states. Each state records predecessor and
successor metadata, WIP, entry/completion policy, and readiness requirements.
State names are descriptive only: custom states are new process steps, not
aliases for Backlog, Ready, Active, Review, or Done. Backlog is a state, not a
second work-item artifact.

The database persists meaningful task events, not worker heartbeats. A future
session resumes from the task state, latest task events, dependencies, checks,
evidence, and current pull capacity. The supervisor is a long-lived live
process, not a durable database object; it may be replaced at any time.

## Pull and flow rules

The coordinator optimizes for pull: downstream capacity requests the next most
ready work. WIP limits constrain task buffering and do not prescribe agent
counts. Serial and parallel task demand remain separate from agent count.
Review WIP is additional to implementation WIP. A full state is an
interrupt signal for the supervisor; it is not a task blocker and must not
create a fake blocked status.

Pull-capacity leases reserve short-lived downstream capacity, not specific
tasks. They may expire or be released without changing task state. Backpressure
must slow upstream admission before new work is started when downstream review
or validation capacity is full.

Worker demand is a property of a task. Serial work uses one reusable worker;
partitionable or fan-out work may use more workers only when independent work
units are already defined. Assurance/control workers must not implement the
same task. Every assignment must have one bounded next action and an expected
progress checkpoint; a worker must not receive an unbounded workstream as one
claim.

## Assurance and control

`specialist_roles` is the reusable role catalog. When a task enters a state
whose policy requires assurance, the helper must enlist every active
specialist role in a required assurance check. This is asserted by the
database from state policy, not from the state name.

One worker may perform multiple assurance and control checks for a task, but
the implementation lane remains separate. Every required check must pass or be
explicitly marked not applicable with a rationale before Done.

Guidance is one versioned `guidance` table containing the former principles
and tenets. `guidance_references` links guidance versions to the research
references supporting them. Guidance is baseline input, not a review-policy
engine.

Design agents must inspect references linked to the intent and task, gather
additional authoritative references when needed, and bind consequential design
decisions to those sources.

## Operating sequence

1. Capture the intent and its type, success criteria, constraints, authority,
   and stop conditions.
2. Research the intent and link reviewed sources.
3. Create bounded Backlog tasks linked to one or more intents.
4. Refine tasks into the configured pullable entry state only when scope, ownership, acceptance, validation,
   dependencies, and specialist assurance checks are present.
5. Pull eligible work within state WIP and downstream capacity.
6. Keep implementation isolated from assurance/control work.
7. Move completed output into the configured review/validation state with
   evidence and resolved checks. Review workers claim that existing review
   state without moving it or replacing the implementation owner, then build
   a fresh brief from current checks, evidence, revision, and task events.
8. Move work into a terminal state only after that state’s required checks and
   evidence qualify it.
9. Re-evaluate the queues after every completion, review result, rework, or
   capacity release; continue until no pullable work remains.

For autonomous execution, read `references/pull-flow.md` and load the
`autonomous-workstream` skill. Use one long-lived supervisor and dynamic lanes;
do not launch one worker per review criterion by default. Compatible review
criteria should be serially consumed by a reusable specialist worker.
If the selected runtime supports detached jobs, the autonomous skill may use
its runtime adapter, but Kanban leases, task claims, evidence, and review
independence remain authoritative.

## Interaction modes

Distinguish the requested operating mode before changing state:

- **status:** inspect and report; do not start or change work;
- **planning/refinement:** clarify, research, split, prioritize, and prepare
  work; do not implement;
- **execution:** pull, dispatch, implement, review, validate, and continue
  until no pullable work remains or an explicit authority, dependency, or
  external condition prevents progress.

Do not treat a completed slice as completion of an execution request.

## Purge discipline

Task purge is explicit and destructive, even though associated task records
are cascaded. Before purging a task, confirm that it is terminal, required
checks and evidence are complete, task events have been reviewed, and no
follow-up, validation debt, or residual-risk decision still depends on it.

## Commands

See [commands](references/commands.md) for the compact helper interface.
Use `status --json` for scheduler-oriented state and `validate` for an explicit
integrity audit.

The command service has a deliberately narrow boundary: it provides
transactional durable state changes, pull selection and claiming, capacity
reservation, task events, checks, evidence, and scheduler-readable status.
The supervisor owns ranking policy, worker dispatch, reuse, liveness, and
inter-agent messages. Do not add persisted worker sessions or a general
command bus to compensate for live coordination.
