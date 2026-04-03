# Integrated Skills Stack

This repository is a working skill stack for improving execution quality over time, not just a collection of unrelated `SKILL.md` files.

## AI Collaboration Note

This project is managed with the aid of an AI coding agent. The skills in this repository were composed and refined conversationally with AI agents under human direction.

The skills are designed to run as a loop:

1. `delegator` coordinates work into explicit lanes with clear exit criteria and validation gates.
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

1. Run execution with `delegator` for active objectives.
2. Capture checkpoints and feedback events with `learning-ledger` during execution.
3. Run `adaptive-reflection` on a defined timeframe (for example, last 2 days) to produce prioritized method deltas.
4. Classify deltas into `project-specific learning` vs `abstract method learning`.
5. Apply approved deltas by updating project-specific artifacts for the first track, and updating/adding skills for the second track.
6. Repeat.

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

## Example Prompts

Use plain human language to trigger the stack behaviors.

Delegated parallel background work (small scope):

- "Please delegate this in the background while we keep planning: update the README examples section, fix any broken links, and report back when done."
- "Queue a small background lane to clean up Makefile comments and keep me posted without blocking this thread."

Delegated parallel background work (large scope):

- "Delegate this as a multi-lane background effort: refactor the skill templates for consistency, add validation checks, and prepare draft commits per lane. Keep the foreground thread free for prioritization."
- "Split this into research, implementation, and verification lanes running in parallel. Keep queue state visible and only block me if a decision is required."

Reflection loop induction:

- "Run a reflection on the last 2 days, classify project-context vs abstract-method deltas, and propose the next reinforcement actions."
- "Improve your methods based on the past week of execution, including evidence-backed changes, deferred hypotheses, and any new skill candidates."

Sample reflection-loop output reports:

- [Reflection Report Samples](docs/reflection-report-samples.md)
- [Delegation-Derived Reflection Backlog Item (Sample)](docs/reflection-report-samples.md#delegation-derived-backlog-item-sample)

## Layout

- [`Makefile`](Makefile): imports local skill directories into this repo
- [`skills/`](skills/): consolidated skill definitions and references
