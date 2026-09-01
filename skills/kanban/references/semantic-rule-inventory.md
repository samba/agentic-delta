# Semantic Rule Inventory

This is the loss-prevention map for suite refactors. Every governing rule has
one canonical owner. Other documents may summarize or link it, but must not
change its meaning. A removed rule is acceptable only when it is mapped here,
replaced by stronger deterministic enforcement, or recorded as deprecated.

## Canonical ownership

| Rule family | Canonical owner | Required behavior |
| --- | --- | --- |
| Durable goals and state | `kanban/SKILL.md` and board schema | Persist a durable intent before substantive autonomous execution; link executable work to it; distinguish intent closure from task completion. |
| Workflow quality | `standard-of-excellence.md` | Preserve research, traceability, independent review, revision-bound proof, safe delivery, and learning invariants. |
| Runtime control | `execution-contracts.md` and board schema | Use immutable autonomy envelopes, explicit gates, bounded retries, cancellation acknowledgement, side-effect receipts, and durable recovery state. |
| Research and reuse | `standard-of-excellence.md` section 4 | Inspect local capability, platform primitives, maintained open source and templates, and standards before custom mechanisms; retain sources, rejected candidates, and the verified gap. |
| Human authority | `standard-of-excellence.md` section 3 | Persist material decisions; ask only after safe inspection/research; never infer approval for privileged, destructive, externally consequential, goal-changing, or high-risk actions. |
| Stage and rework semantics | `execution-contracts.md` | Producers own handoff quality; evaluators own applicability and recommendations; route a defect to the earliest stage able to repair it. |
| Specialist interoperability | `specialist-handoff.schema.json` and `specialist-coordination.md` | Persist required expertise as implementation-neutral specialist classes; validate one contract vocabulary; a recommendation is advisory and cannot move state, expand authority, accept risk, or authorize delivery. |
| Evidence | `execution-contracts.md` | Bind criterion, probe, result, environment, producer, location, and exact revision or digest. Tests or agent confidence alone cannot close non-trivial work. |
| Board policy | `kanban/SKILL.md` and `board-walk.md` | Enforce WIP, dependencies, readiness, review, closure proof, and explicit validation debt. |
| Learning data | canonical Kanban database | Record material transitions, decisions, evidence outcomes, rework, costs, and outcomes atomically where possible. |
| Learning analysis | `learning-ledger/SKILL.md` | Query, aggregate, archive, and report canonical events and metrics; do not create a parallel source of workflow truth. |
| Method promotion | `adaptive-reflection/references/promotion-policy.md` | Separate project context from reusable method; require evidence, stability, research or user applicability signal, portability, overlap and boundary checks, evaluation, review, and rollback. |
| Built-in quality | `built-in-quality.md` | Pin sourced principle/tenet versions; translate assurance into production obligations; use point-of-creation feedback; stop abnormal propagation; require obligation evidence before closure. |
| Controlled improvement | `built-in-quality.md` and `adaptive-reflection` | Experiment on a visible tenet baseline with pinned assignment, measures, exclusions, decision, versioned promotion, and rollback; manage the system constraint rather than local utilization. |
| Project specialist participation | `project-specialists-and-bugs.md` and canonical database | Enroll every active class at project capture; preserve specialist guidance as proposals until adopted; invoke every enrolled class for existing-codebase review and bug disposition. |
| Bugs | `project-specialists-and-bugs.md` and canonical database | Capture observed/expected discrepancy early; require all enrolled specialist dispositions before priority; rank with remaining goal work; action through a linked governed task; resolve only after its task is Done. |
| Domain judgment | applicable Agentic SRE skill | Define stage-specific inputs, analysis, evidence, and advisory recommendation without assuming coordinator authority. |
| Source history | source history packaged within the applicable skill | Link consequential principles and preserve superseded interpretations rather than rewriting history. |
| Skill packaging | each independently installable skill directory | Keep every behavior-critical contract, source history, template, and helper inside the skill package; repository-level `docs/`, sibling skills, and uninstalled checkout paths are non-normative and cannot be runtime dependencies. |

## Non-negotiable integration invariants

- Goal -> decision/research -> design -> task -> validation criterion -> exact
  evidence remains traversable.
- Source -> principle version -> tenet version -> frozen guidance -> assurance
  obligation -> exact evidence -> observed outcome remains traversable.
- Each expected gate is applied or has a recorded `not-applicable` rationale
  from its evaluator; the coordinator may not fabricate a specialist result.
- Product, architecture, implementation, security, supply-chain, independent
  review, delivery/readiness, and operational evidence remain selectable gates.
- Work stays within recorded path, tool, network, credential, cost, time,
  concurrency, retry, and side-effect authority.
- Missing proof, stale proof, unresolved blockers, unaccepted residual risk, or
  unacknowledged validation debt prevents closure.
- A restart uses persisted state and receipts; conversation memory is not proof
  that an operation completed.
- Method changes are versioned, source-backed, evaluated, reviewable, and
  reversible; learning never grants authority to rewrite its own controls.

## Agent output migration

The database contains no legacy handoff state and accepts only canonical gate
and handoff values. Agents migrating older output habits must follow
[agent-handoff-migration.md](agent-handoff-migration.md); ingestion does not
retain aliases or compatibility encodings.

## Refactor audit record

For each consolidation record the old location, new canonical location,
classification (`preserved`, `strengthened`, `conditional`, or `deprecated`),
and behavioral test. Do not classify a rule as deprecated merely because it is
duplicated; first preserve its strongest semantics in the canonical owner.

### 2026-08-31 consolidation

| Previous behavior or location | Classification | Canonical disposition |
| --- | --- | --- |
| Compound domain results (`architecture-pass`, `release-clear`, `required-follow-up`, and similar) | deprecated | Handoff v2 separates `gate_id`, applicability, recommendation, status, and finding severity; ingestion rejects the old values. |
| Fused stage values (`applied`, `skipped-not-applicable`, `blocked`, `rework`) | deprecated | Applicability, recommendation, and execution status are separate in both SQLite and the interchange document. |
| Old named stage chain (Interview through Commit/PR) | deprecated as persisted vocabulary | Six canonical lifecycle stages are used; useful detailed retry checkpoints remain conditional guidance. |
| Delegation instructions loaded for all Kanban work | conditional | Load only for work that actually uses multiple lanes or background coordination. Deterministic or single-lane work retains full gates without delegation overhead. |
| Detailed diagnostic recovery catalog loaded on every diagnosis | conditional | Compact diagnostic loop is normative; load the catalog only when the compact loop does not resolve the relevant pattern. |
| Mandatory style-risk preamble for all substantial authoring | deprecated | Surface a style conflict only when it materially changes behavior, security, performance, readability, or maintenance. Correctness and safety precedence remains. |
| Learning-ledger files as a possible parallel live event source | deprecated | Canonical Kanban SQLite is the live source; files remain idempotent legacy import, archive, and interchange formats. |
| Smart-commit message generation as a full specialist gate | deprecated | It consumes revision-bound evidence as a leaf text transformation; commit execution still requires authority. |
| Software-delivery skill coordinating workers and independent review | deprecated | Delta coordinates dispatch, isolation, review, and rework; delivery produces implementation and verification evidence. |
| Systems-engineer-assist repeating architecture, security, supply-chain, delivery, and readiness gates | deprecated | It owns target-environment compatibility and routes cross-domain findings to the owning specialist. |
| Security review reproducing general license, maintenance, capacity, release, recovery, and support assessments | deprecated | Security consumes the responsible specialist's evidence and evaluates security/privacy/control implications. |
| Full source-register reading for ordinary stable execution | conditional | Read mapped source sections when a version-sensitive claim, governing principle, refresh, or supersession is involved; project-specific research remains required where decisions depend on it. |
| Per-skill copies of specialist enrollment, guidance, existing-codebase review, bug-triage, handoff vocabulary, and coordinator-authority mechanics | preserved and consolidated | Delta's project-specialist contract and SRE's specialist-handoff contract own the common mechanics; each skill retains its domain focus, workflow, evidence, and pass criteria. |
| Separate `Gate` and `Boundary` sections in short lifecycle skills | preserved and consolidated | A single `Result` section retains the gate id, pass condition, routing, and domain authority limit; the common coordinator boundary remains canonical in the handoff contract. |
| Functionally critical skill links to repository-level `docs/` | deprecated anti-pattern | Package the relevant contract and source history inside each skill and validate local links in isolation. Top-level documentation may remain explanatory but non-normative; no synchronization script is used. |

No research, reuse, traceability, autonomy-envelope, human-decision,
independent-review, evidence, rework, cancellation, delivery-safety,
validation-debt, learning, or historical-source invariant was deprecated.
