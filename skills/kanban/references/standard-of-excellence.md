# Agentic Development Standard of Excellence

Use this reference for every durable objective coordinated through this skill
suite. It defines the minimum conformance contract. Project policy may make a
control stricter, but must not silently weaken one. Any accepted exception must
name its owner, rationale, affected scope, expiry or review condition, and
residual risk.

Canonical lifecycle, handoff, gate, and rework semantics are defined in
[execution-contracts.md](execution-contracts.md). Canonical rule ownership and
legacy normalization are defined in
[semantic-rule-inventory.md](semantic-rule-inventory.md).

## Desired Outcome

A human can state a goal in ordinary language, continue using the foreground
thread, make only the decisions that require human authority or judgment, and
later inspect a durable evidence chain from the original goal through research,
decisions, work, validation, acceptance, and learning.

## Conformance Invariants

### 1. Durable intent before substantive execution

- Treat an explicit durable objective (for example, “my goal is”, “achieve”,
  “build”, or “run workstream”) as a request to persist an intent unless the
  user says the discussion is exploratory or plan-only.
- Capture the goal contract before substantive delegated work. Include the
  objective, measurable success criteria known so far, constraints, non-goals,
  autonomy mode, approval boundaries, and stop conditions.
- Acknowledge the generated intent id. Never make the human restate a goal
  merely to fit command syntax.
- If persistence is unavailable, keep an explicit in-session contract and
  disclose that durability is degraded; do not imply that a backlog exists.

### 2. Controlled autonomy

- Deterministic orchestration owns state transitions, WIP, budgets,
  permissions, approval gates, retries, cancellation, and irreversible side
  effects. Agents own bounded research, planning, implementation, and review
  judgment within those controls.
- Select the least autonomous pattern that meets the objective: deterministic
  operation, prompt chain, router, parallel workers, orchestrator-workers, or
  evaluator-optimizer. Record why added agentic complexity is justified.
- Define time, cost, retry, write-scope, tool, network, and concurrency budgets
  before autonomous execution. A missing platform budget is an explicit risk,
  not permission for an unbounded loop.
- Issue those controls as an immutable, persisted autonomy envelope. A worker
  cannot expand its own envelope; expansion requires a recorded authority
  decision and a newly issued run contract.
- Use clean isolated workspaces for concurrent or mutating lanes. Prevent
  overlapping write ownership unless the coordinator sequences integration.

### 3. Human decision protocol

Ask the human only when the answer cannot be established safely from current
evidence and materially changes scope, product behavior, architecture, risk
acceptance, permissions, cost, or an irreversible action.

For each blocking decision:

- persist one decision record linked to its intent and, when applicable, task;
- state the question, two or three viable options when choices are known, the
  recommended/default option, impact of delay, and safe work that can continue;
- separate a factual clarification from an authority decision;
- never treat silence as approval for a high-impact action;
- after the human answers, record the answer, rationale, decider, and affected
  downstream artifacts before resuming them.

Batch independent decisions to reduce interruption. Ask the smallest question
that unlocks the largest amount of safe work.

### 4. Research and provenance

- Research begins with project-local evidence, then current primary sources,
  standards, official documentation, and original research. Vendor guidance is
  useful but must be labeled and should not be the sole support for a general
  control when a primary source exists.
- Every consequential external claim or adopted principle must have a link,
  title, publisher, retrieval date, topic, concise finding, relevance, known
  constraint, review state, and content hash or immutable version when
  practical.
- Link sources to the intent and tasks they informed. Preserve earlier records
  when a source or interpretation changes; append a superseding finding rather
  than rewriting historical conclusions without trace.
- Distinguish source statements, local observations, and agent inference.
  Record rejected alternatives and why they were rejected.
- Refresh time-sensitive claims before they govern new work.
- Before designing a new mechanism, perform a reuse assessment covering local
  dependencies, platform-native capabilities, maintained open-source libraries
  and templates, and relevant standards. Prefer a well-known maintained
  solution; custom implementation requires a documented capability gap,
  rejected candidates, and accepted maintenance burden.

### 5. Readiness and traceability

- An implementation slice may start only when its requirements map through:

  `goal -> decision/research -> design -> task -> validation probe -> evidence`

- Readiness is evidence-based, not a model confidence claim. Do not use a
  numeric confidence threshold as a substitute for satisfied entry criteria.
- Each slice must be coherent, bounded, independently verifiable, reversible
  where practical, and linked to an intent.
- Preserve out-of-scope findings as linked follow-up work; do not silently
  expand the active slice.

### 6. Verification and acceptance

- For governed work, freeze a scope- and policy-versioned review plan covering
  every active specialist class for both proactive assurance and independent
  control. The default is required; only an attributable policy rule or the
  matching specialist may determine not-applicable. Assurance constrains work
  before production; control evaluates the revision before acceptance.
- Prefer deterministic evidence: compilation, tests, static analysis, schema
  checks, security scans, reproducible commands, and observable behavior.
- The implementer runs pre-handoff checks. A fresh reviewer context evaluates
  requirements, design fit, correctness, security, compatibility, test quality,
  and unnecessary scope.
- Self-reported success, agent confidence, or passing tests alone cannot close
  non-trivial work. Acceptance requires an independent review decision and an
  evidence manifest mapped to acceptance criteria.
- Route failures to the earliest stage that owns the defect. Bound repair
  loops and escalate repeated failure patterns rather than retrying unchanged.
- Bind evidence to the exact artifact revision and criterion. A work-profile
  change stales its plan. Policy exceptions and specialist opt-outs remain
  distinct, attributable not-applicable dispositions.
- Freeze the effective principle/tenet guidance with that plan. Assurance is
  not satisfied by consultation alone: translate each material contribution
  into a production obligation, authorized rejection, or attributable
  not-applicable disposition. Required unresolved guidance blocks production;
  unsatisfied obligations and unresolved stop-quality signals block closure.
- Prefer feedback at the point of creation. Use downstream control review to
  validate the capable process and residual judgment, not as the routine means
  of manufacturing quality after defects have propagated.

### 7. Safe delivery and operations

- Least privilege, deny-by-default network access, secret isolation, typed tool
  inputs, output validation, idempotency, and explicit approval protect every
  side-effecting lane.
- Use protected branches and staged, observable, reversible delivery when the
  environment supports them. Record rollback or no-rollback rationale.
- Maintain correlated goal, task, run, artifact, and decision identifiers in
  events. Redact secrets and apply project retention policy.
- Pause or stop must prevent new dispatch while preserving enough state for a
  safe resume.

### 8. Learning without self-authorized drift

- Record material transitions, corrections, decisions, validation results,
  costs, and outcomes in the learning ledger.
- Measure flow and quality together: WIP, throughput, work-item age, cycle time,
  first-pass acceptance, rework, escaped defects, rollback, human override,
  cost, and latency where available.
- Changes to skills, prompts, models, tools, policies, or thresholds are
  versioned changes. They require source-backed rationale, regression
  evaluation, review, and rollback information; an agent must not silently
  rewrite its own governing controls.
- Identify the current system constraint from evidence and subordinate dispatch
  to end-to-end throughput rather than local worker utilization. Improve a
  visible tenet baseline through scoped, measured, reversible experiments; a
  promoted result creates a new version and preserves prior assignments.

## Goal-to-Outcome Protocol

1. **Capture:** persist the goal contract and acknowledge its id.
2. **Triage:** classify risk, ambiguity, autonomy mode, budgets, and human
   authority boundaries.
3. **Discover:** inspect local context and coordinate bounded research; persist
   sources and findings.
   Enroll every active specialist class at project capture so each discipline
   can contribute sourced project principles or actionable tenets early enough
   to guide both new production and review of existing work.
4. **Decide:** infer safe facts; persist and ask only material human decisions.
5. **Design:** produce the smallest coherent architecture and slice plan.
6. **Validate design:** independently test traceability, risks, and proof plan.
7. **Execute:** pull ready work into isolated, WIP-limited lanes.
8. **Verify:** gather deterministic evidence and map it to criteria.
9. **Review:** independently accept, reject, or route bounded rework.
10. **Deliver:** commit or propose changes, stage rollout where applicable, and
    retain rollback evidence.
11. **Close:** realize the intent only when all required linked work is accepted;
    otherwise report blockers, decisions, deferred work, and residual risk.
12. **Learn:** record outcomes and propose reviewed method deltas.

A request to review an existing codebase invokes every enrolled specialist
through the normal assurance/control plan. A discovered bug is captured before
diagnosis is complete, receives every enrolled specialist's explicit
assessment or opt-out, is prioritized against remaining goal work, and becomes
a linked governed task before correction.

The coordinator may overlap research, refinement, and independent lanes when
dependencies and ownership permit. The numbered list expresses obligations and
causal order, not a requirement for wasteful serial execution.

## Stop And Escalation Conditions

Stop affected work and notify the human when any of these occurs:

- required authority, credential, or permission is absent;
- the requested outcome conflicts with a governing principle;
- a decision materially changes the goal or accepts high residual risk;
- provenance is too weak for a consequential design choice;
- scope, cost, time, retry, or WIP budget is exhausted;
- the same failure pattern reaches the autonomous-loop checkpoint threshold;
- validation cannot establish an acceptance criterion;
- a destructive or externally consequential action lacks explicit authority;
- safe cancellation, rollback, or isolation cannot be established.

## Conformance Report

At closure report:

```text
Goal: <intent id and objective>
Outcome: realized|partial|blocked|deferred|rejected
Decisions: <resolved and open ids>
Sources: <linked reference ids and refresh state>
Work: <accepted, deferred, and follow-up cards>
Evidence: <criterion -> proof>
Exceptions: <control, owner, rationale, expiry, residual risk>
Operations: <delivery, observation, rollback>
Learning: <ledger checkpoint and proposed method deltas>
```

## Source Basis

The principle-to-source map, authority notes, and historical vendor inputs are
maintained in [source-register.md](source-register.md). Keep that register
append-only for superseded interpretations and update its review date whenever
the standard is materially revised.
