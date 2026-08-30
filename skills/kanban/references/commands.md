# Workflow Commands

Read this reference first when a user message contains a workflow command.
Canonical commands define behavior. Deprecated spellings should guide the user
without suppressing an otherwise clear substantive request.

## Deprecated Commands

Deprecated command spellings should produce a concise replacement hint when
they are unambiguously invoking a workflow command. Do not let a spelling hint
replace an answer to an ordinary conversational question.

| Deprecated phrase | Replacement |
| --- | --- |
| `walk the board` | `walk board` (equivalent conversational alias) |
| `do kanban loop` | ambiguous: use `walk board` for one maintenance pass or `run workstream <goal>` for autonomous queue-drain |
| `do kanban flow` | `run workstream <goal>` |
| `map the viable autonomous work stream` | `map workstream <goal>` |
| `delegate async` | `start background work <goal>` |
| `async <verb>` | `start background work <goal>` |
| `enter delegator mode` | no mode exists; use explicit commands |
| `exit delegator mode` | no mode exists; use explicit commands |
| `active <verb>` | foreground work is default; restate the desired action directly |

Warning shape for genuinely ambiguous or retired commands:

```text
Deprecated workflow command: `<phrase>`.

No work was started.

Use `<replacement>`.
```

When a deprecated phrase has multiple possible replacements, list the choices
and ask the user to restate the command. Do not infer intent.

## Canonical Commands

### Status

- `work status`: report current board state, active/background lanes, blockers,
  validation debt, review items, and next pullable work. Do not start new work.

### Task creation

Use `task add` to create an executable work item. It requires at least one
existing intent link and stores scope, dependencies, exit criteria, validation,
themes, and optional plan context in the task record. New tasks start in
`Backlog`; use `--column Ready` only when the required readiness fields are
complete. Do not use `backlog add` for executable work items.

All board inspection and mutation must use the bundled kanban helper. Direct SQL
and alternate SQLite clients are prohibited, including for read-only inspection.
When a required query or mutation is unavailable, raise a tooling-improvement
request to the user instead of bypassing the helper.

### Board Maintenance

- `walk board`: run one bounded board-maintenance pass, then report. Inspect
  Review, Active, Ready, Blocked, and Backlog. Do not queue-drain.
- `review completed work`: review cards waiting for acceptance and their proof.
  May use reviewer lanes. Do not implement new work.
- `close completed work`: move independently reviewed, proof-backed cards to
  Done. Do not implement new work.
- `refine intents`: split, clarify, research, and improve intents. Do
  not implement.
- `prepare next work`: fill/refine the Ready queue through clarification,
  splitting, research, and readiness validation. Do not implement unless paired
  with an execution command.

### Planning

- `plan work <goal>`: clarify the goal, inspect context, and produce an
  implementation and validation plan. Do not execute.
- `map workstream <goal>`: map viable autonomous sequence, dependencies,
  parallel lanes, gates, exclusions, stop conditions, and approvals. Do not
  execute until the user follows with an execution command.

### Background Execution

- `start background work <goal>`: create coordinator/lane records, dispatch
  background work, report what is queued/running, then return foreground
  control. The foreground thread must not perform substantive implementation.
- `run workstream <goal>`: autonomous queue-drain. Keep dispatching pullable
  work until no work remains except blocked, permission-gated,
  manual-review-only, or deferred work. The foreground thread is for status,
  approvals, blockers, and exceptions.
- `resume background work`: resume paused background work after revalidating
  assumptions, blockers, and autonomy boundaries.

### Background Control

- `pause background work`: stop dispatching new lanes and preserve state.
- `stop background work`: stop autonomous execution and close or interrupt
  workers where safe. Preserve enough state to resume manually later.

## Precedence

1. Deprecated command gate.
2. Exact canonical command.
3. Explicit user instructions in the same message.
4. General kanban routing by intent.

Exact commands override ordinary assistant autonomy. For example, `start
background work` forbids active-thread implementation after dispatch even when
the work is small.
