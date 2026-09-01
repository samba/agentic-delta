# Workflow Source Register

Last substantive review: 2026-08-31.

This register preserves why the suite adopted its controls. Do not remove a
superseded source or interpretation. Mark it superseded, add the replacement,
and state what changed. Prefer stable canonical URLs; record a retrieval date
in project kanban reference records when a source informs a specific goal.

## Normative and primary foundations

| Principle or structure | Source | How it informs this suite | Authority and limits |
| --- | --- | --- | --- |
| Explicit workflow, WIP control, pull, active management, and flow metrics | [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/) | Project-declared columns and transitions, hard WIP controls, pull discipline, board walks, and WIP/throughput/age/cycle-time measurement | Canonical community guide for Kanban. It does not define agent safety or software validation. |
| Lifecycle governance, scoped use, human oversight, documented testing, monitoring, and independent assessment | [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) and [NIST AI RMF 1.0](https://doi.org/10.6028/NIST.AI.100-1) | Continuous governance; explicit human/agent roles; risk mapping; independent TEVV; production monitoring | Voluntary cross-sector risk framework. Tailor controls to context and applicable law. |
| Generative-AI risk management across govern/map/measure/manage | [NIST AI 600-1 Generative AI Profile](https://doi.org/10.6028/NIST.AI.600-1) | Pre-deployment evaluation, provenance, incident handling, and explicit risk treatment for agent-generated artifacts | Cross-sector profile, not a substitute for domain-specific assurance. |
| Lifecycle-spanning proactive practices, review of existing software, and later verification | [NIST SP 800-218, Secure Software Development Framework 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | Supports early specialist assurance that shapes requirements and production, review/analysis of human-readable code, and later control evidence | Security-focused framework; the suite generalizes the timing and review pattern to other specialist disciplines and must evaluate those extensions empirically. |
| Least privilege, constrained tools, downstream authorization, and human approval for high-impact actions | [OWASP LLM06: Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) | Tool gateway boundaries, permission scoping, and human decision gates | Security guidance focused on LLM applications; it does not define delivery flow. |
| Provenance as attributable entities, activities, agents, derivation, versioning, and reproducibility | [W3C PROV Overview](https://www.w3.org/TR/prov-overview/) | Linked goal/task/source/artifact history and preservation of superseded context | W3C provenance family overview; the suite uses a lightweight relational representation, not full PROV serialization. |
| Verifiable artifact provenance and checking evidence against expectations | [SLSA v1.2 Provenance](https://slsa.dev/spec/v1.2/provenance) and [Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts) | Evidence manifests, source/build lineage, isolated production, and verification separate from generation | Supply-chain standard; not every project can claim a SLSA level. Never imply conformance without its required controls. |
| Correlated traces, metrics, logs, and context propagation | [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/) and [context propagation](https://opentelemetry.io/docs/concepts/context-propagation/) | Correlated goal, task, run, artifact, and decision identifiers across execution events | Observability standard. Collection must still honor privacy and retention policy. |
| Required review and status checks on protected branches | [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | Independent approval and deterministic merge gates where GitHub is used | Platform-specific implementation guidance, not a universal requirement to use GitHub. |
| Multi-turn, trajectory-aware agent evaluation using deterministic and complementary graders | [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Regression sets, isolated runs, task-success and policy-compliance measures, and evidence-backed promotion | Vendor engineering guidance published in 2026; grader validity remains use-case dependent. |
| Empirical limits on reliable completion of longer tasks | [METR: Measuring AI Ability to Complete Long Tasks](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/) | Bounded slices, checkpoints, escalation, and evidence before autonomy expands | Empirical benchmark research; task distributions do not represent every project. |
| Durable recovery and replay require persisted workflow state and retry-safe activities | [Temporal documentation](https://docs.temporal.io/) and [AWS idempotency guidance](https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/) | Run attempts, checkpoints, cancellation, idempotency keys, and side-effect receipts | Product documentation supplies implementation patterns, not a requirement to adopt either platform. |
| Atomic state/history commits and database-enforced relational invariants in the project-local store | [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html), [SQLite constraints](https://www.sqlite.org/lang_createtable.html#ckconst), and [SQLite triggers](https://www.sqlite.org/lang_createtrigger.html) | Kanban mutations and learning events share one transaction; typed links use foreign keys; deterministic record and cross-record rules use constraints and triggers so alternate clients cannot bypass them | SQLite guarantees apply to the database transaction, not external side effects, contextual judgments, or exported artifacts. |
| Customer value, capable process steps, flow, pull, standard work, and continuous improvement | [Lean Thinking and Practice](https://www.lean.org/lexicon-terms/lean-thinking-and-practice/) and [What is Lean?](https://www.lean.org/explore-lean/what-is-lean/) | Goal-to-outcome value streams, bounded WIP, point-of-work guidance, and evidence-backed improvement of a visible standard | Lean Enterprise Institute methodology; the suite's relational translation is a local implementation that requires outcome evaluation. |
| Build quality into production rather than depending on downstream inspection | [W. Edwards Deming Institute: cease dependence on inspection](https://deming.org/quotes/cease-dependence-on-inspection-to-achieve-quality-eliminate-the-need-for-inspection-on-a-mass-basis-by-building-quality-into-the-product-in-the-first-place-3/) | Assurance must become production obligations and fast feedback; control review validates rather than manufactures quality | A foundational quality principle, not a claim that uncertain product or market outcomes can be guaranteed. |
| Detect abnormalities at their source, stop propagation, and institute countermeasures | [Lean Enterprise Institute: Jidoka](https://www.lean.org/the-lean-post/articles/lean-roundup-jidoka/) | Quality signals, containment, affected-work stops, causal analysis, and recurrence checks | Manufacturing-derived methodology generalized to knowledge work; stop scope must remain proportional to impact. |
| Standardized work is the baseline for kaizen | [Lean Enterprise Institute: Standardized Work for Kaizen](https://www.lean.org/the-lean-post/articles/standardized-work-for-kaizen-define-achieve-maintain-improve/) | Versioned tenets, pinned assignments, measured experiments, promotion decisions, and rollback | Practitioner guidance; experiment design and measures remain context-dependent. |
| Define the goal, identify and exploit the constraint, subordinate other work, elevate, and repeat | [TOCICO: Introduction to the Theory of Constraints](https://learningcenter.tocico.org/courses/Introduction-to-the-Theory-of-Constraints) | First-class flow-constraint evidence, buffers, and exploit/subordinate/elevate actions; dispatch optimizes system throughput rather than local utilization | TOCICO educational material. Constraint identification remains an empirical judgment and must not be inferred from utilization alone. |
| Eliminate overproduction, waiting, excess processing, inventory, and correction while preserving flow and pull | [Lean Enterprise Institute: Lean Operations](https://www.lean.org/explore-lean/operations/) | Measure assurance/control queues and reuse valid baselines instead of multiplying repetitive review inventory | Review elimination is never automatic; explicit applicability and residual risk remain required. |

## Agentic workflow pattern sources

| Principle or structure | Source | Adopted interpretation | Caveat |
| --- | --- | --- | --- |
| Prefer simple, composable workflows; distinguish workflows from agents; use chaining, routing, parallelization, orchestrator-workers, and evaluator-optimizer selectively | [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Least-autonomous-fit routing and evaluation before adding multi-agent complexity | Vendor engineering guidance, published 2024; tooling details may age. |
| Measurable outcomes, observe-think-act loops, context, governance, staged rollout, and auditability | [Read AI: How to Build AI Agentic Workflows](https://www.read.ai/articles/how-to-build-ai-agentic-workflows) | Goal contracts, context assembly, human gates, monitoring, and rollback | Vendor publication; product and quantitative claims are not normative. |
| Outcome definition, end-to-end workflow mapping, approvals, secure content access, and multi-agent specialization | [Box: Agentic workflows](https://blog.box.com/agentic-workflows) | Map systems, decisions, handoffs, and approvals before execution | Vendor publication; examples favor content-management use cases. |
| Task-ready inputs, context assembly, isolated execution, PR output, AI review then human judgment, and infrastructure metrics | [Codegen: Agentic coding workflows](https://codegen.com/how-to-build-agentic-coding-workflows/) | Structured task contracts, clean workspaces, review layers, and cost/timeout/diff monitoring | Vendor publication; platform claims require independent evaluation. |
| Single-responsibility agents, small tool surfaces, external prompts, workflow/MCP separation, containerization, and simplicity | [Bandara et al.: Production-Grade Agentic AI Workflows](https://arxiv.org/html/2512.08769) | Thin protocol adapters, modular prompts, bounded tools, and deployment isolation | Preprint centered on one media-generation case study. Multi-model consensus is not treated as proof of correctness. |

## Suite-local interpretations requiring evaluation

The following are deliberate local policies rather than direct requirements of
one source:

- review-first pull order and weighted-shortest-job-first prioritization;
- the exact intent lifecycle and default board columns;
- stage-owned applicability records;
- retry/checkpoint counts in the autonomous loop;
- ledger retention windows and 1 MB compressed artifact caps;
- the distinction between project-context and abstract-method learning.
- the assurance/control policy matrix and its initial work-type exceptions,
  including early design and discovery code-convention exceptions.
- the default principle/tenet registry, exact guidance precedence, inherited
  stop-signal tenet, obligation taxonomy, and experiment/constraint records;
- default enrollment of every active specialist at project capture;
- all-specialist assurance/control treatment of an existing-codebase review;
- one pending bug disposition per enrolled specialist and the exact requirement
  to complete every disposition before project-relative prioritization;

Retain these while outcomes support them. Recalibrate through
`adaptive-reflection` using measured flow, quality, cost, and user-override
evidence. Do not describe them as requirements of the external sources above.

## Maintenance protocol

When new evidence changes a principle:

1. Add the new source with title, publisher, canonical URL, publication or
   version date, retrieval date, topics, and authority classification.
2. Record which principle, skill, reference, task, and decision it affects.
3. Preserve the former interpretation and mark it `superseded on <date> by
   <reference>`.
4. State whether the new evidence confirms, narrows, contradicts, or extends
   the prior interpretation.
5. Evaluate the changed workflow against historical regression cases before
   adoption.
6. Record the approved delta and rollback condition in the learning ledger.
