---
name: adaptive-reflection
description: Use when reflecting over a defined timeframe or improving agent methods from durable outcomes, corrections, costs, failures, and workflow metrics; separate project lessons from reusable method changes and gate any promotion with research and evaluation.
---

# Adaptive Reflection

Produce a timeframe-bounded, evidence-based retrospective that improves future
work without allowing learning to rewrite its own controls. Kanban provides
workflow state; the learning ledger provides events and metrics; this skill
interprets evidence and proposes reviewed changes.

Read the [method promotion policy](references/promotion-policy.md) before
adopting any project-process or reusable method change. It is the canonical
source for partitioning, evidence, stability, applicability, research,
portability, overlap, boundary, evaluation, review, and rollback gates.

For enrollment, guidance proposals, existing-codebase review, and bug triage,
follow the Kanban
[project-specialist contract](../kanban/references/project-specialists-and-bugs.md).
This specialty contributes measurable learning/improvement guidance; reviews
systemic workflow deficiencies; and assesses bugs for recurrence, escape,
rework, and learning impact.

## Workflow

1. Resolve the requested time window to absolute timestamps and state any
   ambiguity.
2. Collect thread corrections and decisions, linked intents/tasks/runs,
   commits/diffs/tests/logs, gate outcomes, rework, costs, duration, human
   overrides, delivery outcomes, and prior method baselines.
3. Audit what was known before execution, what was assumed, and which
   assumptions were acted on without verification.
4. Classify each significant outcome as value, neutral churn, or negative
   value, and each miss as `preventable` or `non-preventable` with evidence.
5. Identify repeated success and failure mechanisms rather than merely listing
   events. Include skipped-stage disputes, weak handoffs, design-validation
   failures, validation debt, scope drift, repeated rework, and coordinator
   bypass attempts when present.
6. Partition every candidate into `project-context`, `abstract-method`, paired,
   or deferred and apply the promotion policy before proposing adoption.
7. Research precursor practices and established solutions for every proposed
   method change. Record authority, version/date, retrieval date, finding,
   relevance, limits, and relation to the previous basis.
8. Define the smallest reinforcement, evaluation, regression limit, and
   rollback condition. A valid result may be “no material evidence for a
   method change.”
9. Update project artifacts only for accepted project-context changes. Update
   reusable skills only for accepted abstract-method changes, and only within
   the current write and approval authority.
10. Persist remaining research, hypotheses, and follow-ups in their respective
    tracks.

For “improve your methods,” include standing methodological backlog items in
the window, but do not lower promotion gates to clear the backlog.

## Required Output

Use [the reflection template](references/reflection-output-template.md), while
treating the promotion policy—not repeated template wording—as normative.
Return:

- timeframe and evidence coverage;
- highest-signal value, friction, corrections, and preventability findings;
- a priori knowledge and assumption audit;
- project-context actions;
- abstract-method candidates with every promotion gate result;
- accepted changes with baseline, evaluation, regression and rollback data;
- deferred/rejected candidates and reasons;
- research and hypothesis backlogs;
- stability or deprecation notes for prior promoted rules;
- calibration of routing weights or thresholds only when outcome evidence
  actually supports a change.

Templates for detailed capture are
[skill delta](references/skill-delta-template.md) and
[research backlog](references/research-backlog-template.md). They are output
formats, not additional policy sources.

## Authority Boundary

Reflection may recommend changes. It may not weaken security, permissions,
autonomy, evidence, review, or release controls; promote a project observation
without the policy gates; treat one success or failure as sufficient evidence;
or silently replace historical rules and sources. A change beyond current
authority remains a proposal for human review.
