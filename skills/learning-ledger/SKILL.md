---
name: learning-ledger
description: Use when querying, aggregating, exporting, retaining, or analyzing durable workflow events and Kanban metrics for reflection, trend analysis, audit, or process evaluation. Kanban remains the canonical event-producing workflow.
---

# Learning Ledger

The learning ledger is an analytics and retention view over the canonical
Kanban database. It does not define task transitions, gates, autonomy, or a
parallel event source. Normal Kanban operations should record their material
events atomically; use this skill for explicit observations, queries, metric
snapshots, aggregation, archival, and legacy import.

For enrollment, guidance proposals, existing-codebase review, and bug triage,
follow the Kanban
[project-specialist contract](../kanban/references/project-specialists-and-bugs.md).
This specialty contributes non-distorting measurement/learning guidance;
reviews missing outcome, quality, flow, and operational feedback; and assesses
bugs for systemic trend and recurrence significance.

## Data Rules

- Link events to available intent, task, run, attempt, gate, decision,
  criterion, artifact, and exact revision identifiers.
- Preserve event time, producer, event type, outcome, evidence location, and
  schema/derivation version. Distinguish observation from inference.
- Record material transitions, corrections, decisions, rework, validation
  outcomes, delivery/rollback, human overrides, costs, latency, and final
  outcomes; avoid low-value narration.
- Redact secrets, credentials, personal data, proprietary excerpts, and
  unneeded prompt/tool payloads. Apply project retention policy.
- Append corrections or superseding events; do not rewrite historical events.
- Metrics are derived evidence, not performance targets or authority to change
  policy. Preserve their query window and derivation version.
- A learning record cannot move work, pass a gate, accept risk, expand
  permissions, or alter the method that governs it.

The packaged [event schema template](references/event-schema-template.md)
describes explicit observation fields. The SQLite schema and Kanban helper are
authoritative when they differ from legacy file formats.

## Workflow

1. Identify the question, time window, scope, identifiers, and retention or
   privacy constraints.
2. Query the canonical database before legacy archives. Do not double-count an
   imported event and its archived source.
3. Add an explicit learning event only when the observation was not already
   captured by a state-changing Kanban operation.
4. Create versioned metric snapshots for reproducible trend comparisons.
5. Aggregate flow and quality together: WIP, throughput, age, cycle time,
   first-pass acceptance, rework, escaped defects, rollback, human override,
   cost, and latency where evidence exists.
6. Report data coverage, missing links, derivation limits, and uncertainty.
7. Archive or prune only according to configured retention, retaining hashes
   and archive receipts needed to detect duplicate imports.

## Helper

Use `scripts/ledger.py` for query, aggregate, archive/export, and legacy import.
Use `kanban/scripts/kanban.py` for canonical event insertion, metric snapshots,
and state-linked atomic operations. Do not edit SQLite or generated aggregates
directly.

The ledger helper retains compatibility with historical NDJSON and compressed
aggregate files. Those files are archive/interchange formats, not a second
live source of truth. Import must be idempotent and must preserve the original
record or its content hash.

## Output

Return the query window and scope, source database/archive, coverage and
missing data, versioned metrics, material event chains, supported trends,
counterevidence, and limitations. When providing input to adaptive reflection,
separate raw observations, derived metrics, and interpretation.
