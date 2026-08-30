# Integrated Skills Stack

This repository is a working skill stack for improving execution quality over time, not just a collection of unrelated `SKILL.md` files.

## AI Collaboration Note

This project is managed with the aid of an AI coding agent. The skills in this repository were composed and refined conversationally with AI agents under human direction.

The skills are designed to run as a loop:

1. `kanban` coordinates work into explicit lanes with clear exit criteria and validation gates.
2. `learning-ledger` records what happened (decisions, checkpoints, corrections, outcomes) in structured history.
3. `adaptive-reflection` analyzes that history and converts recurring patterns into concrete process/skill updates.

## Net Effect

Used together, the stack produces compounding behavior:

- better near-term delivery through clearer decomposition and coordination,
- lower rework via explicit validation and blocker handling,
- improved long-term method quality from evidence-backed reflection,
- tighter separation between project-specific adjustments and reusable, general method improvements,
- continuous self-upgrade of existing skills,
- creation of new skills when repeated patterns justify a new reusable workflow.

In short: execution generates evidence, evidence drives reflection, reflection upgrades existing skills and spins out new ones when needed.

## Learning Tracks

The integrated flow separates learning into two tracks:

- `project-specific learning`: context-bound lessons tied to a specific repository, architecture, backlog, or operating constraints. These updates belong in project docs/process and should not be generalized as reusable skills.
- `abstract method learning`: portable workflow improvements that remain valid after removing project-specific details. These updates belong in reusable skills and may justify new skill creation.

This distinction prevents method drift and keeps reusable skills clean while still capturing high-value local project learning.

## Intended Use

Use this project when you want an operational feedback system for agent work, especially for multi-step or parallelizable objectives where quality, traceability, and method improvement matter.

Typical use pattern:

1. Run execution with `kanban` for active objectives.
2. Capture checkpoints and feedback events with `learning-ledger` during execution.
3. Run `adaptive-reflection` on a defined timeframe (for example, last 2 days) to produce prioritized method deltas.
4. Classify deltas into `project-specific learning` vs `abstract method learning`.
5. Apply approved deltas by updating project-specific artifacts for the first track, and updating/adding skills for the second track.
6. Repeat.

Reflection output must include:

- an a priori knowledge audit (known facts, assumptions, and assumptions acted on without verification),
- miss classification for each miss as `preventable` or `non-preventable` with rationale.

## Repository Workflow

Treat this repository as the coordination layer for a skill lifecycle:

1. Fork this repo and customize the skill stack for your team, domain, and operating standards.
2. Adopt skills into each agent runtime by syncing selected directories from this repo into agent homes (for example `~/.codex/skills`, `~/.claude/skills`, `~/.cursor/skills`).
3. Let agents execute, log, and reflect so skills evolve through real usage.
4. Periodically run `make import` (or `make`) to re-import evolved `SKILL.md` directories from agent homes back into this repo.
5. Review and version those updates, then reshare the refreshed skills with other agents and human operators.

Import mechanics:

- Source skill directories containing `SKILL.md` are copied into `./skills`; destination directories are replaced.
- If duplicate skill names exist across sources, later iteration order in `Makefile` wins.

## Federated Skill Sync

Use [`skill-federation.yaml`](skill-federation.yaml) as the catalog of local
tracking repositories, candidate remote repositories, tutorials, documents, and
published skill artifacts. The catalog is YAML-compatible JSON so the sync
helper can parse it with the Python standard library.

Catalog sources carry policy metadata:

- `trust_status`: `trusted`, `candidate`, `watchlist`, `reference`,
  `rejected`, or `deprecated`.
- `install_policy`: `installable`, `review-required`, `discovery-only`,
  `reference-only`, or `blocked`.
- `review_status`: `unreviewed`, `partially-reviewed`, or `reviewed`.

Use [`scripts/skill_federation.py`](scripts/skill_federation.py) for selective
skill discovery and local installation:

```sh
python3 scripts/skill_federation.py list --query "design validation"
python3 scripts/skill_federation.py install --skill kanban --dry-run
python3 scripts/skill_federation.py install --query "security scanning"
python3 scripts/skill_federation.py install --skill test-strategy --allow-review-required --dry-run
python3 scripts/skill_federation.py update --installed-only
python3 scripts/skill_federation.py remove --skill kanban --dry-run
```

Kanban database access must go through the kanban helper. Agents must not run
direct SQL or alternate SQLite clients, including for read-only inspection. If
the helper lacks a required capability, raise a tooling-improvement request
instead of bypassing it.

The helper supports:

- `list`: search cataloged installed and candidate skills by keyword, source, or
  skill name.
- `install`: copy a selected skill into an agent skill path.
- `update`: refresh matching local skills from local or cached git sources.
- `remove`: remove matching installed skills from the selected agent skill path.

Selectors:

- `--query <keywords>` matches source and skill names, capabilities, keywords,
  and status.
- `--skill <name>` selects an exact skill name. Repeat it for multiple skills.
- `--source <id>` restricts the operation to one catalog source.

Targets and safety:

- By default, installs target `~/.codex/skills`; use `--agent claude`,
  `--agent cursor`, or `--target-dir <path>` for other targets.
- Use `--dry-run` before mutating an agent skill path.
- `install` and `update` refuse `discovery-only`, `reference-only`, and
  `blocked` sources.
- `review-required` candidate sources require `--allow-review-required`.
- `remove` refuses to delete anything outside the selected skill root and
  refuses to delete directories that do not contain `SKILL.md`.
- Runtime operation logs are written under the user-scope skill path by default:
  `~/.codex/skills/.skill-federation/logs/skill-federation.ndjson`.
  Do not store federation runtime logs in this repository.

## Skill Domain Boundary

This repository should only version skills that support the integrated execution-improvement loop: coordination/delegation, work history capture, reflection, learning classification, backlog synthesis, and evidence-backed method updates.

Before adding or syncing a skill into this repo, verify that it belongs to that loop. Systems engineering, Kubernetes, language/config generation, code style extraction, commit-message quality, OpenAI API usage, plugin authoring, document rendering, image generation, and general marketplace/installer skills belong in separate skill stacks unless they directly support the feedback-loop domain here.

`make import` is intentionally broad: it copies every discovered `SKILL.md` directory from supported local agent homes into `./skills`, replacing same-named directories. Treat imported untracked skill directories as review candidates, not automatically accepted repo content. Remove irrelevant imported directories before staging changes.

## Example Prompts

Use plain human language to trigger the stack behaviors.

Background work (small scope):

- "start background work: update the README examples section, fix any broken links, and report back when done."
- "start background work: clean up Makefile comments and keep me posted without blocking this thread."

Background work (large scope):

- "run workstream: refactor the skill templates for consistency, add validation checks, and prepare draft commits per lane."
- "map workstream: split this into research, implementation, and verification lanes, with dependency order and validation gates."

Kanban command grammar and status control:

- `work status` for board state, active/queued lanes, worker assignment, blockers, and recent completion evidence
- `walk board` for one bounded board-maintenance pass
- `plan work <goal>` for planning without execution
- `map workstream <goal>` for autonomous-path mapping without execution
- `start background work <goal>` for queued background execution
- `run workstream <goal>` for autonomous queue-drain until no pullable work remains
- `pause background work` / `resume background work` / `stop background work` for background control
- `review completed work` / `close completed work` for completion handling
- `refine backlog` / `prepare next work` for readiness work without implementation

Deprecated command phrases such as `delegate async`, `async <verb>`, `do
kanban loop`, `do kanban flow`, `enter delegator mode`, and `active <verb>`
should receive a concise replacement hint when they unambiguously invoke a
workflow command. `walk the board` is an accepted conversational alias for
`walk board`; do not reject it or suppress the substantive request.

Reflection loop induction:

- "Run a reflection on the last 2 days, classify project-context vs abstract-method deltas, and propose the next reinforcement actions."
- "Improve your methods based on the past week of execution, including evidence-backed changes, deferred hypotheses, and any new skill candidates."

Sample reflection-loop output reports:

- [Reflection Report Samples](docs/reflection-report-samples.md)
- [Delegation-Derived Reflection Backlog Item (Sample)](docs/reflection-report-samples.md#delegation-derived-backlog-item-sample)

## Layout

- [`Makefile`](Makefile): imports local skill directories into this repo
- [`skill-federation.yaml`](skill-federation.yaml): federated skill source catalog
- [`scripts/skill_federation.py`](scripts/skill_federation.py): selective skill list/install/update/remove helper
- [`skills/`](skills/): consolidated skill definitions and references
