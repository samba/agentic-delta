---
name: adaptive-reflection
description: Use when the user asks to reflect over a timeframe (for example, "reflect on the last 2 days"). Analyze thread outcomes, project changes, failure patterns, useful signals, and convert lessons into skill/process updates plus a focused research backlog.
---

# Adaptive Reflection

## Use This Skill When

Use this skill when the user asks for reflection with a defined timeframe (explicit dates or relative windows like "last 48 hours").

Also use this skill when the user asks to "improve your methods".

## Integration

This skill is part of an integrated method stack with:

- `delegator`: coordinates execution lanes and validation gates.
- `learning-ledger`: provides structured event/checkpoint history for reflection input.

Expected flow:

1. execution is coordinated by `delegator`,
2. events and checkpoints are captured by `learning-ledger`,
3. `adaptive-reflection` analyzes evidence and proposes method/skill updates.

## Goal

Produce a practical, evidence-based retrospective that improves next-iteration quality by:

1. identifying what produced value,
2. identifying what caused churn, rework, interruptions, or correction,
3. tightening methods and criteria,
4. converting lessons into reusable skills and references.

## Operating Rules

- Anchor the reflection to the requested timeframe.
- In "improve your methods" mode, run deeper research and include all standing methodological backlog items in scope.
- Prioritize evidence from:
  - thread interactions and corrections,
  - commits/diffs/tests/logs generated in that timeframe,
  - plan docs and status artifacts.
- Distinguish:
  - high-value outcomes,
  - neutral churn,
  - negative-value work (rework, avoidable complexity, regressions).
- Keep conclusions tied to concrete indicators.
- Default to minimum-complexity process changes.
- Require research support for adopted methodological adjustments.
- If a proposed adjustment is not supported by research, stop and consult the user before adoption.
- Convert durable lessons into skill updates or new skills.
- Create or update supporting reference material for those skills.

## Context Partitioning (Mandatory)

All reflection artifacts must be partitioned into two explicit tracks:

- `project-context`: backlog, hypotheses, and enhancements specific to the active project/repository.
- `abstract-method`: reusable reasoning/workflow improvements independent of any single project or technology stack.

Hard rules:

- Do not leak project-specific policy, naming, paths, variables, or architecture into abstract skills.
- Before analysis, run a classification gate for each topic: assign `track`, `evidence_scope`, and `split_handling`, then record a short reason summary.
- `track` must be one of `project-context` or `abstract-method`.
- `evidence_scope` should state whether the evidence is `project-only`, `cross-project`, or `generic`.
- `split_handling` should state whether the topic is `single-track`, `paired`, or `defer`.
- Run a leakage audit on every `abstract-method` candidate; if it contains project-specific identifiers, keep it in `project-context` or split it into a paired delta.
- If a candidate improvement contains project context, keep it in the project track only.
- For each topic, produce paired outputs when relevant:
  - project-specific delta (applied in project plans/docs/process),
  - abstract skill delta (applied to reusable skill definitions).


## Workflow

1. **Bound the window**
   - Resolve absolute start/end timestamps.
   - State assumptions when the window is ambiguous.

2. **Collect evidence**
   - Extract thread signals: interruptions, corrections, approvals, reversals, explicit dislikes.
   - Extract project signals: commit clusters, reverted work, repeated failure points, test outcomes.
   - Extract plan-state signals: stale plans, blocked lanes, ownership-boundary drift.

2.5. **Classify topics before conclusions**
   - Assign `track`, `evidence_scope`, and `split_handling` for each topic.
   - Record a short reason summary for the classification.
   - Run the leakage audit before any abstract-method delta is accepted.

3. **Assess value and friction**
   - For each major workstream, classify:
     - value delivered,
     - cost/churn introduced,
     - fit to project goals.
   - Identify failure patterns:
     - over-complexity,
     - ownership breaches,
     - premature execution,
     - weak validation strategy.

4. **Extract successful method patterns**
   - Identify methods that repeatedly worked:
     - diagnosis loop quality,
     - decomposition and delegation quality,
     - test gating quality,
     - review/feedback integration speed.
   - Record measurable signals that predicted success.

5. **Define reinforcement actions**
   - Produce concrete practice updates:
     - what to do more,
     - what to stop,
     - what to gate with criteria.
   - Keep each action small, testable, and enforceable.

6. **Encode learnings into two-fold deltas**
   - For each durable lesson, decide whether it belongs to:
     - `project-context`,
     - `abstract-method`,
     - or both (as paired deltas).
   - Update project artifacts only with project-context deltas.
   - Update reusable skills only with abstract-method deltas.
   - Add supporting references (templates/checklists/decision rules) to the matching track.
   - Prefer simple reusable workflows over broad policy prose.
   - When a coordination skill uses weighted routing or thresholds, review whether outcomes justify recalibrating:
     - dimension weights,
     - score thresholds,
     - hard-trigger override rules.
   - Only adjust those values when evidence shows repeated over- or under-routing relative to actual complexity, churn, or validation burden.

7. **Build partitioned backlogs and hypotheses**
   - Maintain separate backlog and hypothesis lists for:
     - `project-context`,
     - `abstract-method`.
   - Keep rationale and validation signals scoped to the same track.
   - Rank each track by expected impact and near-term applicability.

8. **Improve-your-methods mode (when requested)**
   - Resolve all standing methodological backlog items first.
   - Produce only high-confidence, high-relevance adjustments supported by research.
   - Separate:
     - research-backed adjustments (ready to adopt),
     - hypothesis adjustments (require user consultation before adoption).

9. **Return deliverables**
   - Use the template in `references/reflection-output-template.md`.
   - Include:
     - summary of highest-signal findings,
     - prioritized next actions,
     - skill/references created or updated,
     - proposed research subjects.

## Required Deliverables

- A timeframe-bounded reflection report.
- A prioritized list of reinforcement actions.
- A concise reason summary for each topic classification or split decision.
- Two-fold delta list:
  - project-context deltas (project-only),
  - abstract-method deltas (skill-level reusable).
- Two-track research/hypothesis backlog with impact rationale per track.
- In "improve your methods" mode:
  - a backlog-resolution report,
  - a list of research-backed method changes,
  - a separate consultation list for non-research-backed hypotheses.
  - when weighted coordination routing is in use, a short calibration note stating whether current weights and thresholds should stay fixed or be adjusted.

## Reference Material

- Reflection output structure: [references/reflection-output-template.md](references/reflection-output-template.md)
- Skill delta capture template: [references/skill-delta-template.md](references/skill-delta-template.md)
- Research backlog template: [references/research-backlog-template.md](references/research-backlog-template.md)
