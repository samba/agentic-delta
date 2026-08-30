# Validation Contracts

Use validation contracts to make closure proof explicit for kanban cards,
delegated work, background tasks, research outputs, commits, skill changes, and
data pipelines.

## Contract Fields

- `target`: artifact, behavior, claim, commit, card, dataset, or pipeline being validated.
- `scope`: what the validator may inspect.
- `prohibited_scope`: what the validator must not edit, infer, or touch.
- `evidence`: expected proof artifacts.
- `probes`: commands, source checks, database queries, screenshots, manifests, or diff checks.
- `pass_criteria`: concrete conditions for acceptance.
- `risks`: claims or failure modes the validator should try to disprove.
- `handoff`: report shape and reviewer/owner.

## Skill Change Validation

- Inspect `SKILL.md` frontmatter and trigger wording.
- Check direct reference links exist.
- Run helper scripts with `--help` or dry-run examples.
- Confirm no generated caches or unrelated files are included.
- Check domain routing does not duplicate another skill's responsibility.

## Design Validation

Use design validation before implementation for non-trivial software work. The
validator inspects the design artifact, not the eventual code, and decides
whether the task is ready for implementation, needs rework, is blocked, or is
trivial enough for a recorded skip.

Check:

- problem and scope are explicit;
- requirements trace to design decisions, implementation slices, and proof;
- architecture fits existing module boundaries, data/control flow, interfaces,
  ownership, and dependency direction;
- implementation slices are small, ordered, and reversible;
- validation strategy is concrete and proportionate to risk;
- maintainability and local code-style impacts are considered;
- assumptions, alternatives, failure modes, mitigations, and residual risks are
  recorded;
- conditional categories such as security/privacy, data/schema, performance,
  reliability, compatibility, compliance/licensing, UX/accessibility, supply
  chain, and concurrency are either applied or skipped by their own criteria.

Design validation must not be bypassed by the coordinator. Each category or
stage agent owns its own `applied`, `skipped-not-applicable`, `blocked`, or
`rework` record.

## Data Pipeline Validation

- Validate source catalog JSON.
- Compile helper scripts.
- Run a no-secret smoke test.
- Check credential redaction.
- Load a small database if the schema changed.
- Record source/license caveats.

## Research Answer Validation

- Check that claims map to sources.
- Verify latest/current facts were refreshed.
- Confirm proxy metrics are labeled.
- Reproduce at least one key calculation.
- Identify missing source families needed for stronger conclusions.

## Report Shape

```text
Validation: pass|fail|partial
Scope:
- <what was inspected>
Evidence:
- <commands, files, outputs, links>
Findings:
- <issue or pass signal>
Residual risk:
- <remaining caveat or none>
```

For stage validation, include:

```text
Stage: <stage>
Status: applied|skipped-not-applicable|blocked|rework
Criteria:
- <criteria used>
Evidence:
- <proof or observation>
Handoff:
- <next stage or returned stage>
```
