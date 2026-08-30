# Intent And Work-Item Refinement

Use this workflow when the user asks to refine an intent, split scope, clarify tasks, decompose complex work, improve execution readiness, or identify blockers caused by vague candidate work.

## Goal

Turn broad intents into clear plans and smaller executable work items with explicit:

- scope
- dependencies
- implementation strategy
- constraints
- success criteria
- validation
- worker assignment boundaries
- integration paths
- documented decisions for human review

Do not start implementation during refinement unless the user explicitly asks.

## Workflow

1. **Inventory current flow state**
   - List `Review`, `Active`, `Ready`, and intents.
   - Respect WIP limits and existing Active work.
   - Prefer refining items that unblock Active/Ready work or near-term dependency chains.

2. **Find refinement candidates**
   Mark an intent or work item for splitting when it has any of:
   - multiple deliverables in one summary
   - unclear validation surface
   - mixed implementation and evaluation work
   - mixed schema, persistence, runtime behavior, and tests
   - hidden dependencies on uncreated data shapes
   - overlapping scope with another backlog item
   - high ambiguity or high complexity
   - likely parallel lanes with disjoint file ownership
   - unclear producer/consumer handoff between components, generated artifacts,
     runtime state, external services, or validation evidence

   Split out a research-first prerequisite before implementation when the work
   has sensitive design choices or failure modes around operations, security,
   privacy, data movement, network isolation, secrets, backup/restore,
   reliability, scalability, or performance. The research item should inform
   the design early enough to avoid rework, and implementation cards should
   depend on it when its answer changes the safe approach. Its exit criteria
   must require persisted findings, conclusions, and design/implementation
   implications that downstream cards can cite as evidence.

   When a card depends on an integration path, map the path explicitly before
   marking it ready: producer, transformation, transport, persistence boundary,
   runtime handoff, consumer, error/fail-closed behavior, and validation proof.
   If multiple viable paths exist, research or inspect enough evidence to
   compare them and document the selected path plus rejected alternatives.

3. **Classify the item**
   Use one of these outcomes:
   - **Keep**: already executable as a single task.
   - **Refine**: rewrite summary/plan without splitting.
   - **Split**: create smaller backlog records and mark the original as umbrella/context.
   - **Merge/Dedupe**: combine overlapping items or mark one as superseded.
   - **Defer**: useful, but blocked by strategic or architectural uncertainty.

4. **Split by execution boundary**
   Prefer subtasks that can be independently validated:
   - data/schema definition
   - persistence/cache compatibility
   - runtime integration
   - retrieval/scoring behavior
   - answer rendering behavior
   - tests/fixtures/benchmarks
   - documentation/design update

5. **Write explicit task requirements**
   Each resulting backlog record or task card should state:
   - **Scope**: paths/modules/interfaces touched.
   - **Implementation strategy**: first concrete approach, not just outcome.
   - **Constraints**: API compatibility, test data rules, performance budgets, source licensing, WIP boundaries.
   - **Success criteria**: observable behavior or artifact.
   - **Validation**: exact commands or proof artifact.
   - **Dependencies**: upstream cards/backlog records.
   - **Decision record**: what was decided, why it fits the stated project
     goals, what alternatives were rejected or deferred, and what assumptions
     need later validation.

6. **Preserve traceability**
   - Keep the original intent as the human context for resulting work items.
   - Link every resulting work item to one or more intents before `Ready`.
   - Add dependencies from child items to prerequisites.
   - Persist research references with retrieval dates, topics, provenance, and links to the relevant intent/work item.
   - Use `backlog dependency add` for modeled dependencies; store explanatory context in `raw_json` only when the helper cannot represent the nuance.
   - Record decision summaries in backlog notes or revised summaries so the
     human can review and redirect the plan later without reconstructing the
     reasoning from chat history.
   - Avoid deleting backlog records unless the user explicitly asks; prefer marking status/context in-place.

7. **Mark only ready work as Ready**
   Mark a refined item as `Ready` only when scope, success criteria, constraints, implementation plan, and validation are clear enough to meet the project’s readiness rules.

## Output Shape

Report:

```text
Refine
- <id>: <change>

Split
- <old-id> -> <new-id-1>, <new-id-2>

Merge / Umbrella
- <id>: <status/context>

Next Ready Candidates
- <id>: why it is ready / what remains
```

End with the smallest next board operation that improves flow.
