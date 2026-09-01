# Agentic Delta

Agentic Delta is a durable coordination and continuous-improvement suite for
constrained-autonomy software work. A user can state a goal in ordinary
language; the suite persists it, researches and refines it, identifies human
decisions, coordinates bounded work, enforces quality gates, and learns from
the observed outcome.

Delta is the workflow governor. It does not replace product, architecture,
security, implementation, supply-chain, or production specialists. It assigns
implementation-neutral specialist classes and accepts their structured,
evidence-backed recommendations while retaining control of workflow state and
authority.

## Intended Use

Use this suite when work benefits from:

- a durable goal and backlog that survive conversation or worker restarts;
- proactive research before architecture or custom implementation;
- explicit human decisions, constraints, budgets, and approval boundaries;
- multiple specialist perspectives or independently reviewed work;
- traceability from goal through decisions, design, tasks, criteria, and proof;
- autonomous progress within a recorded permission and side-effect envelope;
- bug capture, specialist-informed priority, and governed correction;
- outcome-based learning and controlled improvement of project or agent method.

For a transient question, deterministic one-step operation, or plan-only
conversation, use the least-complex adequate path rather than creating a full
autonomous workstream.

## The Three Skills

- [`kanban`](skills/kanban/) is the coordinator and canonical project-state
  owner. It captures goals, maintains the backlog, records decisions, freezes
  guidance, dispatches bounded work, ingests specialist handoffs, applies
  gates, routes rework, and controls closure.
- [`learning-ledger`](skills/learning-ledger/) queries and analyzes canonical
  Kanban history and metrics. It is not a parallel event store and cannot
  change workflow state or policy.
- [`adaptive-reflection`](skills/adaptive-reflection/) converts evidence over a
  defined period into project improvements or reusable method proposals. It
  cannot promote its own recommendations or weaken governing controls.

Behavioral rules live inside these independently installable skill packages.
This README explains composition; it is not a competing policy source.

## Standard Workflow

The order expresses dependencies and quality obligations. Safe research,
refinement, and read-only review may overlap when ownership and evidence remain
clear.

1. **Capture the goal.** Persist the objective, success measures, constraints,
   non-goals, autonomy mode, approval boundaries, and stop conditions. Link all
   executable work to the durable intent.
2. **Enroll specialist classes.** Ask every active specialist to inspect the
   goal early, propose sourced principles or verifiable tenets, and identify
   missing context or consequential decisions.
3. **Discover and research.** Inspect the project and proven local capability;
   then research standards, platform primitives, maintained open source,
   templates, and established products before proposing custom mechanisms.
   Preserve candidates, rejected alternatives, sources, and verified gaps.
4. **Resolve human decisions.** Ask only questions that safe inspection and
   research cannot settle. Persist the choice, rationale, decider, affected
   work, and safe work that may continue meanwhile.
5. **Design the outcome and proof.** Establish a traceable product and
   architecture contract, quality attributes, risks, failure behavior,
   acceptance criteria, and validation strategy. Independent specialists
   contribute assurance obligations before implementation hardens.
6. **Plan bounded slices.** Create coherent, dependency-aware, reversible tasks
   with explicit ownership, WIP limits, required gates, and immutable autonomy
   envelopes covering paths, tools, network, credentials, cost, retries, side
   effects, cancellation, and escalation.
7. **Execute within the envelope.** Use isolated write ownership where work is
   concurrent. Workers cannot broaden scope or authority, fabricate specialist
   results, or treat confidence as proof.
8. **Verify and review.** Bind criteria to exact artifact revisions and
   reproducible evidence. Apply every expected gate or obtain the assigned
   evaluator's evidenced `not-applicable` disposition. Independently review
   non-trivial work and route defects to the earliest repair stage.
9. **Deliver safely.** Require applicable security, supply-chain, migration,
   rollback, operational-readiness, and authorization evidence. Persist side
   effect and cancellation receipts.
10. **Observe and close.** Realize the goal only when outcome criteria, gates,
    evidence, risk decisions, validation debt, and follow-up disposition are
    complete. Record material outcomes and corrections.
11. **Improve deliberately.** Analyze trends and causal mechanisms, test the
    smallest useful process change, and promote reusable method changes only
    through evidence, research, review, evaluation, and rollback controls.

## Assurance and Control

Delta builds quality into work rather than relying only on inspection:

- **Assurance** specialists contribute guidance and task-specific obligations
  before or during production, tied to frozen tenets and verification methods.
- **Control** specialists independently evaluate the artifact and evidence for
  those obligations.

All enrolled specialist classes are considered by default. A reviewer owns its
applicability decision and may return `not-applicable` with examined scope and
rationale. The coordinator cannot manufacture that result or convert an
advisory recommendation into risk acceptance, permission, or delivery
authority.

## Existing Codebases and Bugs

A request to review an existing codebase invokes every enrolled specialist
against the project goal and effective guidance. Findings identify evidence,
impact, and the earliest repair stage.

A discovered bug is recorded immediately as an observed-versus-expected
discrepancy. Every enrolled specialist provides an applicability and impact
assessment before the coordinator prioritizes the bug among remaining goal
work. Correction proceeds through a linked governed task and normal gates.

## Improvement Strategy

The suite combines built-in quality, Lean flow, constraint management, and
kaizen without allowing learning to rewrite its own controls:

- version principles as durable outcome guidance and tenets as actionable
  standard work with verification methods;
- freeze applicable guidance for each task and derive assurance obligations at
  the point of work;
- track flow, quality, cost, latency, rework, escaped defects, rollback, and
  human overrides together rather than optimizing one metric;
- expose the active constraint and improve it instead of maximizing local
  utilization;
- append corrections and supersessions rather than rewriting history;
- separate project-context learning from portable method change;
- research established practices before changing reusable workflow;
- evaluate improvements against a baseline, regression limits, and rollback.

## Durable State and Helpers

The Kanban SQLite database is the canonical live store. Use
[`kanban.py`](skills/kanban/scripts/kanban.py) for state operations and
[`ledger.py`](skills/learning-ledger/scripts/ledger.py) for analysis, archival,
and legacy import. Do not edit the database directly or treat interchange and
archive files as a second live source of truth.

The handoff JSON schema is an interchange boundary. The database remains the
authority for relational, workflow, evidence, and state constraints, and only
an atomic ingestion receipt establishes acceptance.

## Working With Agentic SRE

[Agentic SRE](https://github.com/samba/agentic-sre) supplies product,
architecture, delivery, security, supply-chain, production, compatibility,
diagnostic, code-convention, and change-record specialist behaviors. Delta
stores required expertise as specialist classes rather than hard-coded skill
names, allowing workers to activate an installed skill from delegated role
context.

The suites remain separate because they have distinct ownership:

- Delta owns durable intent, orchestration, evidence acceptance, authority,
  state transitions, closure, and method improvement.
- SRE skills own domain analysis, production or review work, evidence, and
  advisory gate recommendations.

## Example Prompts

Start and autonomously coordinate a durable product goal:

> My goal is to build and launch a self-service SaaS product for small clinics.
> Persist this goal, research proven and open-source approaches, identify the
> decisions I need to make, and coordinate the work within this repository.
> Do not purchase services, create external accounts, or deploy production
> resources without my approval.

Capture a goal but stop before execution:

> Record a goal to replace our bespoke job scheduler with a maintained
> solution. Research candidates, capture constraints and unresolved decisions,
> and prepare the backlog, but do not implement anything yet.

Review an existing codebase comprehensively:

> Review this codebase against its stated product goal. Enroll every specialist
> class, identify risks and deficiencies with evidence, route each finding to
> the earliest repair stage, and propose a prioritized improvement backlog.

Register and prioritize a bug:

> Record a bug: users can submit the payment form twice when the first request
> is slow. The expected behavior is at-most-once order creation. Obtain
> specialist impact assessments, prioritize it with the existing backlog, and
> action it when its rank and dependencies permit.

Ask for a decision-focused status update:

> Report goal and board status, current WIP, gate state, blockers, validation
> debt, and the next pullable work. Ask me only the material decisions that are
> currently preventing safe progress.

Run evidence-gated improvement:

> Reflect on the last 30 days of completed work. Analyze flow and quality
> together, distinguish project lessons from reusable method changes, research
> established approaches for each method proposal, and recommend only changes
> with an evaluation and rollback plan.

## Installation and Federation

Each directory beneath [`skills/`](skills/) is independently installable.
[`skill-federation.yaml`](skill-federation.yaml) catalogs public repositories
and packages; [`skill_federation.py`](scripts/skill_federation.py) supports
selective listing, installation, update, and removal.

```sh
python3 scripts/skill_federation.py list --query "software architecture"
python3 scripts/skill_federation.py install --skill kanban --dry-run
python3 scripts/skill_federation.py update --installed-only
```

Install reviewed sources at pinned revisions. Runtime logs belong in the
configured user skill path, not this repository.

## Repository Scope

This repository contains coordination, durable workflow state, learning-data
analysis, and evidence-gated method improvement. Domain specialist skills
belong in their respective suites. Repository-level documents may provide
examples or maintainer context, but functionally critical resources must remain
inside the relevant skill directory.
