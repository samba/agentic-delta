# Specialist Coordination

Use this reference when selecting expertise for research, a design choice,
design or implementation review, release readiness, or another independent
gate. Kanban records specialist classes; it never selects a skill package by
name.

## Profile work before review planning

From the goal, risk surfaces, quality attributes, architecture, change scope,
and validation strategy, determine which disciplines must:

- `inform`: supply evidence or constraints before a decision;
- `produce`: create the specialist-owned artifact or analysis;
- `review`: independently evaluate an artifact or implementation.

Persist the work type, lifecycle stage, artifact kinds, risk attributes,
classification rationale, and derived scope hash. Then freeze a review plan
against an active policy version. The plan materializes every active specialist
class twice:

- `assurance`: proactive contribution to constraints, patterns, risks, and
  acceptance criteria, using the `inform` role before substantive production;
- `control`: independent inspection for errors, omissions, drift, and weak
  evidence, using the `review` role before acceptance.

The invariant fallback is applicable and required. Versioned policy rules may
declare a narrow exception or condition for a work type, stage, class, and
purpose. An unmatched, ambiguous, or unevaluable exception never silently
removes review: ambiguity blocks planning and an unevaluable condition remains
pending for specialist determination.

Create a project-specific class only when no default expresses the needed
discipline. New classes affect new plans, not an already frozen class/version
snapshot. Registry membership is not proof that a matching worker is
available.

Every active class is enrolled when a project intent is captured. Enrollment
makes the class available for early goal-context consultation, project-guidance
proposals, existing-codebase review, and bug assessment; it does not bind the
class to a particular skill implementation. Ingesting a project-linked handoff
marks that enrollment consulted while preserving the class version used.

For an explicit existing-codebase review, do not risk-narrow participation:
create the comprehensive plan so every active/enrolled class receives assurance
and control work or records not-applicable. For a bug, every enrolled class must
assess goal impact or opt out before the coordinator assigns its backlog rank.

Every class has a stable id, human title, and self-contained role context. The
context describes expertise, concerns, expected output, and boundaries in
natural language, for example:

```text
You are a systems security specialist. Evaluate identity, authorization,
trust boundaries, abuse cases, deterministic controls, and security evidence.
Do not accept residual risk or authorize release.
```

```text
You are a specialist in production operations for SaaS products. Evaluate
service objectives, observability, capacity, deployment safety, recovery,
incident ownership, and controlled launch evidence.
```

Do not mention a repository or skill implementation in the class. Different
installed skills, tools, or human specialists may satisfy the same class.

## Default registry

New and existing databases receive these versioned active classes without
overwriting a project-local class having the same id:

| Class id | Scope represented |
| --- | --- |
| `workflow-governance` | Durable coordination, constrained autonomy, gates, traceability, and closure |
| `workflow-learning` | Ledger analysis, workflow metrics, reflection, and evidence-gated method improvement |
| `software-product-discovery` | Users, problems, outcomes, requirements, constraints, and viable product slices |
| `software-architecture` | Reuse research, boundaries, contracts, quality attributes, decisions, and architecture slices |
| `software-delivery` | Bounded implementation, maintainability, risk-selected validation, and revision-bound proof |
| `software-supply-chain` | Provenance, dependencies, licenses, vulnerabilities, pinning, SBOMs, and replacement |
| `security-privacy-compliance` | Threats, controls, privacy, customer trust, audit evidence, and assurance obligations |
| `production-operations` | Reliability, observability, capacity, recovery, incidents, support, and controlled launch |
| `systems-compatibility` | OS, distribution, runtime, tool, deployment, and rendered-artifact compatibility |
| `systems-diagnostics` | Known-good comparison, falsifiable hypotheses, discriminating probes, and evidence recovery |
| `code-conventions` | Evidence-based, language-scoped project coding conventions |
| `structured-language-engineering` | Corpora, grammars, parsers, validation, generation, and measured conformance |
| `kubernetes-operations` | Explicit-context, least-privilege Kubernetes inspection and troubleshooting |
| `change-record-quality` | Thread- and task-informed working-draft partitioning, revision-grounded commits, and durable change summaries |

The registry covers the capability scope currently supplied by both suites. A
new plan covers every active class for both purposes; documented policy rules,
not coordinator omission, encode exceptions. The registry deliberately does
not encode skill names or repository locations. Inspect a
class with `specialist class show <class-id> --context-only` and dispatch that
exact versioned context. Registry updates create new versions; existing gate
assignments retain their selected version.

Projects initialized before specialist class version 2 retain their pinned
`change-record-quality` context. Update that class through the helper when the
project wants topic-aligned draft partitioning; do not edit the registry tables
directly or silently change already frozen review assignments.

## Resolve policy and dispatch

Policy `normally-not-applicable` and false conditional rules create durable
not-applicable plan items with the exact policy rule and rationale. Required,
reviewer-determined, and unevaluable conditional items create gate requirements.
Assurance items attach to `assurance-readiness`; control items attach to
`independent-review`. Dispatch each worker
with:

1. the stored role context, preferably as the opening instruction;
2. intent, task, run, attempt, gate, and specialist-class identifiers;
3. scoped artifact and question;
4. autonomy envelope and allowed evidence access;
5. required version-2 handoff, exact class version, review purpose, and plan-item id.

Available skills should activate from the described specialist context and
task, not because the coordinator names them. The worker returns the exact
assigned class, role, version, and its own worker id.

## Gate aggregation

Every recorded requirement must be satisfied before the gate can pass. Kanban
aggregates specialist handoffs deterministically:

- any blocked handoff blocks the gate;
- otherwise any failed handoff routes the gate to rework;
- otherwise all satisfied or reviewer-marked not-applicable requirements pass the gate;
- a pending requirement keeps the gate pending.

The gate evaluator is the set of contributing worker ids. A control
requirement needs an independent handoff. Only a matching specialist handoff may mark its
requirement `not-applicable`; direct status edits without a matching handoff
are rejected. Policy exceptions need no worker but remain attributable to the
pinned policy rule. Each plan pins its scope, policy, class set, and class
versions. A scope-profile change makes the plan stale; later class or policy
updates affect future plans only.

Selecting a class does not grant permissions, accept risk, or authorize
delivery. A specialist may identify an additional discipline; the coordinator
persists that as a new requirement before dispatching it.
