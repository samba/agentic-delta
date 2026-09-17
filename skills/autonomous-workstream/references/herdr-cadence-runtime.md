# Herdr/Cadence Runtime

Use this reference only when Herdr and Cadence are the selected execution
backend for autonomous work. Kanban remains authoritative for task sequence,
dependencies, WIP, eligibility, timing, gates, evidence, review, and closure.

## Purpose

Use Herdr for persistent, inspectable agent processes and Cadence for the lead
and worker coordination loop. Do not build a second supervisor unless this
integration fails a required capability test.

```text
Kanban policy and evidence
        |
        v
Cadence lead and bounded assignments
        |
        v
Herdr panes and worktrees
        |
        v
Codex/Claude workers
        |
        v
Kanban claims, evidence, review, and closure
```

Herdr state is execution telemetry, not proof of acceptance. A worker's pane
must still produce the claim, progress evidence, handoff, and review records
required by Kanban.

## Prerequisites

The initial supported target is Linux, one user, Git, Codex workers, and a
project-local configuration. Pin versions before adoption and verify the
installed commands rather than assuming compatibility.

- Herdr 0.7.5 or later.
- Cadence installed as a Herdr plugin.
- Git with worktree support.
- The selected worker harness, initially Codex.
- A user-owned runtime directory and project-local `.cadence.toml`.

Claude support must remain a separate compatibility check; Cadence documents it
as untested in the initial integration path.

## Setup

Verify the runtime first:

```sh
herdr --version
herdr agent get
herdr status server
```

Install and initialize Cadence:

```sh
herdr plugin install zhenyufu/herdr-cadence
herdr plugin action invoke herdr-cadence.init
```

Review and commit the generated `.cadence.toml`. Start conservatively:

```toml
schema_version = 2
enabled = true
yolo = false
agent_default = "generalist"

[lead]
harness = "codex"
max_parallel = 1

[agents.roles.generalist]
description = "Executes one bounded implementation or research increment"
runners = ["codex-default"]
version_control_mode = "git-worktree"

[agents.runners.codex-default]
harness = "codex"
```

Start and inspect the lead:

```sh
herdr plugin action invoke herdr-cadence.start
herdr plugin action invoke herdr-cadence.status
```

Use `max_parallel = 2` only after the single-worker recovery test passes. Use
shared-checkout only for explicitly serialized write ownership. Keep approval
prompts enabled until interruption, recovery, and cancellation have been
verified.

## Responsibility Mapping

Kanban selects the candidate and enforces policy. Cadence receives only the
eligible assignment and manages lead/worker prompts. Herdr launches and keeps
the worker process visible, persistent, interruptible, and attachable.

The integration must not treat Cadence or Herdr state as a second task board.
The adapter should translate only these execution facts back to Kanban:

- worker launch and identity;
- claim acceptance;
- heartbeat and health observation;
- bounded progress and artifacts;
- worker completion or failure;
- cancellation and recovery events.

Acceptance, gate applicability, review, rework, and closure remain Kanban
operations. Workers must not receive the human Kanban client surface or direct
database access.

## Status Authority

Use one status authority per Herdr pane. Prefer a complete lifecycle
integration; otherwise use Herdr's process detection and screen-manifest
fallback. Do not combine two competing lifecycle authorities for the same pane.

Semantic states are operational observations only: `working`, `blocked`, and
`idle`. Display labels such as indexing or waiting are metadata, not workflow
states. Unknown or idle observations never justify acceptance or destructive
cancellation without runtime evidence.

## Required Proof

Run this small proof before increasing concurrency or adding another
orchestration plugin:

1. Start two disjoint bounded assignments with `max_parallel = 2`.
2. Verify both workers are visible in Herdr and claim through the Kanban adapter.
3. Verify each emits a durable checkpoint and compact delta.
4. Interrupt one worker deliberately.
5. Start a fresh lead or recovery pass and reconstruct the orphaned claim.
6. Fence the old attempt and create a linked successor without duplicate work.
7. Record review/rework and verify final user-visible behavior end to end.

If any step fails, record the smallest missing runtime primitive. Do not add a
custom controller or another plugin merely to hide the failure.

## Optional Components

Add a socket client or MCP bridge only when Cadence's integration surface lacks
a required operation. Add Dagr only as a read-only DAG or attention renderer
after the core workflow passes; it must not become a second workflow authority.

## Upstream Repositories

- [Herdr runtime](https://github.com/herdrdev/herdr): terminal-native agent
  runtime, panes, state detection, persistence, and socket API.
- [Herdr documentation](https://herdr.dev/docs/): installation, agent state,
  integrations, and API behavior.
- [Awesome Herdr](https://github.com/yigitkonur/awesome-herdr): ecosystem index;
  use it for discovery, not as proof that every listed project is production
  ready.
- [Herdr Cadence](https://github.com/zhenyufu/herdr-cadence): lead/fleet
  orchestration, role profiles, worktrees, and bounded concurrency.
- [Herdr Python client](https://github.com/54rt1n/herdr-python-client): optional
  zero-dependency socket automation reference.
- [Herdr Go socket client](https://github.com/lib-x/herdr-sock-go): optional
  typed Go socket integration reference.
- [Herdr simple MCP](https://github.com/54rt1n/herdr-simple-mcp): optional
  stateless MCP bridge with role-scoped tool profiles.
- [Herdr Dagr](https://github.com/aemrebarut/herdr-dagr): optional read-only
  workflow visualization; defer until core proof passes.
