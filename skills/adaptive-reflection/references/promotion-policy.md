# Method Promotion Policy

Use this policy when reflection proposes a project-process change, reusable
skill change, prompt/model/tool change, autonomy threshold, routing rule, or
gate-policy change.

## Partition first

Classify every candidate before drawing a promotion conclusion:

- `project-context`: repository-specific policy, naming, paths, architecture,
  or constraints;
- `abstract-method`: portable reasoning or workflow behavior independent of a
  particular project.

Record evidence scope (`project-only`, `cross-project`, or `generic`), handling
(`single-track`, `paired`, or `defer`), applicability realm (`project-only`,
`project-family`, or `discipline-general`), and applicability signal
(`user-assertion`, `field-research`, `both`, or `none`). Remove project names,
paths, confidential examples, and local architecture from abstract candidates.
Split paired lessons rather than leaking project context into a reusable skill.

## Promotion gates

An abstract method change requires all of:

1. **Evidence:** at least two independent evidence points or queue cycles with
   concrete references, unless the user explicitly establishes the behavior as
   a broadly applicable preference.
2. **Stability:** a recheck or follow-up observation, not one noisy incident.
3. **Applicability:** explicit user assertion in portable terms, external
   discipline research, or both.
4. **Research:** authoritative support for the consequential principle and a
   record of whether it confirms, narrows, contradicts, or extends the prior
   basis.
5. **Portability:** the rule remains actionable after project context is
   removed.
6. **Overlap:** no existing skill or smaller clarification already owns it.
7. **Boundary:** explicit exclusions prevent expansion into unrelated cases.
8. **Evaluation:** named baseline, representative evaluation set, expected
   improvement, separate task-success and policy-compliance measures,
   regression limits, and rollback condition.
9. **Review:** reviewed, versioned adoption with the previous policy retained.

A new skill additionally requires material distinctness, repeated need, a
split/merge rationale, and explicit user confirmation.

## Decision precedence

Apply the first rule that decides the outcome:

1. Keep project-specific lessons in project artifacts.
2. Defer a single noisy incident until repeated evidence exists.
3. Make the smallest update to an existing owner when it already covers the
   behavior.
4. Reject a change that weakens the owner's core purpose or a governing safety
   invariant.
5. Keep reusable but unsupported ideas as hypotheses.
6. Adopt the smallest portable, evidence-backed, bounded update after its
   regression evaluation passes.
7. Create a new skill only when the additional new-skill conditions pass.
8. Deprecate or revert an adopted rule when later evidence shows increased
   ambiguity, churn, rework, policy failure, or regression.

No reflection result may expand its own permissions or silently modify the
controls governing the evaluation or adoption. Preserve the previous rule,
source interpretation, evaluation, and rollback/deprecation record.
