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

### Goal declaration

- Ordinary language such as `my goal is <goal>`, `achieve <goal>`, or an
  equivalent explicit durable objective invokes goal capture without requiring
  a special command. Persist a goal contract, acknowledge its intent id, and
  default to background coordination unless the user requests planning only,
  immediate foreground execution, or queue-drain.
- `declare goal <goal>` is an explicit equivalent. It captures first, then
  performs triage and dispatch under the standard of excellence.
- Goal declaration authorizes persistence and coordination inside the stated
  scope. It does not authorize privileged, destructive, production, financial,
  publishing, or other externally consequential actions.

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

Canonical learning data follows the same rule. Use `event add/list`, `metric
snapshot/list`, and `archive add`, or the learning-ledger wrapper that calls
those APIs. Structured events reside in `.kanban/kanban.db`; compressed daily
and aggregate files are derived exports, not a competing source of truth.

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

For all goal and execution commands, read `standard-of-excellence.md` and
persist material authority decisions with `decision add/resolve`. Use
clarifications for missing facts; do not disguise a risk-acceptance or product
choice as a factual clarification.

### Specialist Handoffs

Profile the work and freeze its assurance/control plan before dispatch:

```bash
python3 skills/kanban/scripts/kanban.py review profile set \
  <task-id> <work-type> <Discover|Design|Implement|Verify|Deliver|Observe> \
  [--artifact-kind <kind>] [--risk-attribute <attribute>] \
  --classified-by <identity> --rationale <text>
python3 skills/kanban/scripts/kanban.py review profile show <task-id>
python3 skills/kanban/scripts/kanban.py review plan create \
  <plan-id> <task-id> [--policy <id>] [--policy-version <n>]
python3 skills/kanban/scripts/kanban.py review plan show <plan-id>
python3 skills/kanban/scripts/kanban.py review plan list [--task <task-id>]
python3 skills/kanban/scripts/kanban.py guidance show <plan-id>-guidance
```

The plan covers every active class for assurance and control. Policy exceptions
remain visible; pending items require specialist dispatch.

Translate required tenets and assurance findings into production work before
pulling the task into Active:

```bash
python3 skills/kanban/scripts/kanban.py obligation add \
  <obligation-id> <plan-id>-guidance <tenet-id> test \
  "Run the compatibility contract during implementation" Implement \
  --verification "reproducible contract test" --owner <worker> \
  --artifact <artifact> --review-plan-item <assurance-item-id>
python3 skills/kanban/scripts/kanban.py obligation satisfy \
  <obligation-id> <passing-evidence-id>
```

An assurance handoff may atomically provide the same records through its
optional `obligations` array. Use `principle list` and `tenet list` to inspect
the governing registry. Adding a project principle requires an outcome,
rationale, authority classification, and any supporting reference ids.

Store a project tenet or a draft experimental variant without rewriting prior
versions:

```bash
python3 skills/kanban/scripts/kanban.py tenet store \
  <tenet-id> <theme> <title> <instruction> --effect <outcome> \
  --verification <proof-method> --principle <principle-id> \
  [--reference <reference-id>] [--draft]
python3 skills/kanban/scripts/kanban.py tenet override \
  <override-id> <tenet-id> <required|advisory|not-applicable|exception> \
  '<scope-json>' --rationale <text> --authorized-by <identity> \
  [--decision <id>] [--expires-at <epoch>] [--rollback-condition <text>]
```

An exception or not-applicable override requires a linked decision. Overlapping
active overrides that both match a task are rejected as ambiguous.

Run a scoped tenet experiment only with a draft variant:

```bash
python3 skills/kanban/scripts/kanban.py experiment add \
  <experiment-id> <principle-id> <baseline-tenet> <draft-variant-tenet> \
  <problem> <hypothesis> '<scope-json>' '<exclusions-json>' '<metrics-json>' \
  --owner <identity> --rollback-condition <text>
python3 skills/kanban/scripts/kanban.py experiment status <id> running
python3 skills/kanban/scripts/kanban.py experiment assign \
  <id> <task-id> <baseline|variant>
```

Assign before freezing guidance. Terminal experiment states require an
authorized decision id. Record the active flow constraint with `constraint
set`; use `quality-signal open` to stop affected Active work and
`quality-signal resolve` only after causal fields, countermeasure, and recurrence
test are known.

### Project specialists and existing work

Project capture enrolls every active specialist. Inspect the registry and start
a comprehensive existing-codebase review with:

```bash
python3 skills/kanban/scripts/kanban.py project specialists <intent-id>
python3 skills/kanban/scripts/kanban.py codebase-review start \
  <review-task-id> <intent-id> <scope-or-revision> \
  [--objective <goal-relative-review-objective>] [--owner <coordinator>]
python3 skills/kanban/scripts/kanban.py guidance-proposal list \
  <intent-id> [--status proposed]
python3 skills/kanban/scripts/kanban.py guidance-proposal resolve \
  <proposal-id> <accepted|rejected> [--adopted-id <principle-or-tenet-id>] \
  [--decision <decision-id>]
```

Store accepted guidance with `principle add` or `tenet store` before resolving
its proposal. A rejection requires a linked decision. Handoff proposals are
advisory and never alter effective guidance automatically.

### Bugs

Capture a discrepancy before full diagnosis, then obtain every enrolled
specialist disposition before priority is finalized:

```bash
python3 skills/kanban/scripts/kanban.py bug register \
  <bug-id> <intent-id> <summary> --observed <behavior> --expected <behavior> \
  --reporter <identity> [--reproduction <steps>] [--environment <context>] \
  [--evidence <reference>]
python3 skills/kanban/scripts/kanban.py bug assess \
  <bug-id> <class-id> <applicable|not-applicable> \
  --rationale <text> --assessed-by <identity> \
  [--goal-impact <0-100>] [--urgency <0-100>] [--risk-summary <text>]
python3 skills/kanban/scripts/kanban.py bug prioritize \
  <bug-id> <rank> --rationale <goal-relative-reason>
python3 skills/kanban/scripts/kanban.py bug action \
  <bug-id> <task-id> --owner <worker>
python3 skills/kanban/scripts/kanban.py bug list [--intent <intent-id>]
python3 skills/kanban/scripts/kanban.py bug show <bug-id>
```

Applicable assessments require impact, urgency, and risk. Actioning preserves
the bug rank in its linked backlog task; ordinary refinement, readiness,
assurance, control, and evidence rules then govern the correction.

Add or update a specialist class only when the implementation-neutral defaults
do not express the required discipline:

```bash
python3 skills/kanban/scripts/kanban.py specialist class add \
  <class-id> <title> <role-context> [--description <text>]
python3 skills/kanban/scripts/kanban.py specialist class update \
  <class-id> <title> <role-context> [--description <text>]
python3 skills/kanban/scripts/kanban.py specialist class list [--all]
python3 skills/kanban/scripts/kanban.py specialist class show \
  <class-id> [--version <n>] [--context-only]
python3 skills/kanban/scripts/kanban.py specialist gate require \
  <gate-id> <class-id> <inform|produce|review> --rationale <text>
python3 skills/kanban/scripts/kanban.py specialist gate list <gate-id>
```

Use the stored role context as the delegated worker's opening specialist
instruction. Do not put skill names in the class or dispatch contract.

```bash
python3 skills/kanban/scripts/kanban.py handoff validate <document.json> \
  [--expected-task <task-id>] [--expected-run <run-id>]
python3 skills/kanban/scripts/kanban.py handoff ingest <document.json> \
  [--expected-task <task-id>] [--expected-run <run-id>]
python3 skills/kanban/scripts/kanban.py handoff show <handoff-id>
python3 skills/kanban/scripts/kanban.py handoff list [--task <task-id>]
```

`validate` does not accept the handoff or update workflow records; it proves
shape plus current workflow semantics against the selected database.
`ingest` atomically persists normalized records and returns the durable receipt.
Do not treat schema validation alone as acceptance.

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
