# Herdr/Cadence Integration

Use this reference when autonomous-workstream runs inside Herdr. The pattern
is provider-neutral, with Codex shown as the lead and Codex/Claude as workers.

This procedure was verified against the successful integration in
`../neurogen/docs/HERDR_CADENCE.md` and `../neurogen/tooling/herdr-cadence.sh`
on 2026-09-15. Treat those files as local precedent and verify current command
options before copying them elsewhere.

## Design rule

Use a dedicated named Herdr session for autonomous work; keep the default
session interactive. Herdr provides session execution, Cadence launches the
lead/workers, and Kanban remains authoritative for objective, task, claim,
checkpoint, evidence, blocker, review, and closure state. Dagr is optional.

## Setup

The runtime contract, responsibility mapping, and canonical configuration
shape live in [Herdr/Cadence runtime](herdr-cadence-runtime.md); this reference
focuses on user-facing setup commands and guarded control keywords.

From the target Git repository:

```sh
herdr --version
git rev-parse --show-toplevel
herdr session attach <project>-autonomous
herdr --session <project>-autonomous workspace create \
  --cwd "$PWD" --label <project> --no-focus
herdr --session <project>-autonomous plugin install \
  zhenyufu/herdr-cadence --yes
```

Create and commit `.cadence.toml` before using worktrees:

```toml
schema_version = 2
enabled = true
yolo = false
agent_default = "generalist"

[lead]
harness = "codex"
max_parallel = 1

[git]
auto_integrate = true
cleanup_on_success = true

[agents.roles.generalist]
description = "Executes one bounded work increment"
runners = ["codex-default"]
version_control_mode = "git-worktree"

[agents.runners.codex-default]
harness = "codex"
```

Start with one worker. Increase concurrency only after interruption/recovery
passes; use shared-checkout only with serialized path ownership.

## Guarded commands

Use a project-local wrapper requiring `HERDR_SESSION` and mapping:

```text
preflight -> herdr --session "$HERDR_SESSION" status server
             herdr --session "$HERDR_SESSION" workspace list
cadence validate-config -> herdr --session "$HERDR_SESSION" plugin action invoke herdr-cadence.validate-config
cadence status          -> herdr --session "$HERDR_SESSION" plugin action invoke herdr-cadence.status
cadence start           -> herdr --session "$HERDR_SESSION" plugin action invoke herdr-cadence.start
```

Do not invoke `start` unless preflight and validation pass. A Herdr launch and
matching Kanban claim are required before work is active.

## User command keywords

- `start background work`: preflight, validate, start the lead, dispatch eligible work;
- `work status`: read-only Herdr/Cadence/Kanban status;
- `monitor status`: recurring bounded status-delta loop;
- `pause workflow`: stop new dispatch and preserve claims;
- `resume workflow`: preflight, recover orphaned claims, and resume eligible work;
- `recover work`: reassess active tasks without responsive workers;
- `stop workflow`: orderly cancellation with acknowledgements;
- `validate cadence`: preflight and configuration validation only;
- `show workers`: correlate Herdr worker state with Kanban claims.

## Context transfer and recovery

Give each worker one immutable briefing. Afterward, send only deltas:

```text
DELTA task=<id> checkpoint=<id>
PROOF: <artifact, test, or evidence id>
BLOCKER: <id and unblock condition, or none>
NEXT: <one bounded action>
```

When an `Active` task has no responsive worker, read its Kanban reconstruction
packet, inspect Git/filesystem state against the attempt baseline, classify the
attempt, record evidence, fence the old attempt, and create a linked successor
when needed. Resume from the fresh briefing and checkpoint, never a full chat
transcript.

## Verification gate

Before increasing concurrency or adding Dagr, prove one small objective with a
clean/baselined repository, one worker, durable checkpoint/delta, deliberate
interruption, fresh-session reconstruction, old-attempt fencing, no duplicate
work, review, and end-to-end user-visible proof.

## References

- Herdr docs: <https://herdr.dev/docs/>
- Awesome Herdr: <https://github.com/yigitkonur/awesome-herdr>
- Cadence: <https://github.com/zhenyufu/herdr-cadence>
