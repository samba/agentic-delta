# Intents, Research, And Legacy Migration

For durable human goals, apply `standard-of-excellence.md`: capture the goal
contract before substantive work, link research and decisions, and preserve
superseded source interpretations rather than overwriting their history.

## Intent model

An intent is a human-originated objective that is worth understanding or
achieving but is not yet actionable. Its `kind` may be `idea`, `problem`,
`concern`, `opportunity`, or `question`; these are natural-language categories,
not separate workflows.

Intent states are `captured`, `researching`, `refining`, `planned`, `deferred`,
and `closed`. A closed intent requires exactly one closure reason:
`realized` or `rejected`.

Work items use the board columns. Every work item must have one or more intent
links before it enters `Ready`; exploratory work may remain in `Backlog` while
its relationship is clarified. Worker/session identity is coordination
metadata, not human ownership.

## Research references

Research workers must retain reusable references with URL, title, publisher,
publication date when available, retrieval date, topics, summary, relevance,
design constraints, provenance, and links to the relevant intent and/or work
item. Uncertain metadata is recorded as unknown and flagged for review.

## Legacy migration

Migration is non-destructive, repeatable, and report-producing. The current
helper exposes the historical reference pass as `migrate references`; full
legacy intent classification remains a follow-on migration operation. It must use
the kanban helper or a helper capability explicitly added for migration; agents
must not query or mutate the database directly with SQL. If migration requires
an unsupported operation, pause and raise that tooling gap to the user.

1. Inventory legacy records, IDs, timestamps, statuses, links, notes, events,
   validation evidence, and stored worker reports.
2. Map human objectives to intents and executable records to work items.
3. Preserve original IDs and source metadata.
4. Recover URLs and citations from descriptions, plans, clarifications, events,
   validation evidence, and raw JSON.
5. Normalize and deduplicate references, link them to their source intent or
   work item, and mark uncertain records `needs_review`.
6. Classify legacy terminal records explicitly. Map only known cases to
   `closed/realized` or `closed/rejected`; leave ambiguous cases for review.
7. Emit counts for mapped, linked, deduplicated, ambiguous, skipped, and failed
   records.

Repeated migration must not duplicate intents, work items, links, or references.
Legacy commands and fields remain compatibility aliases only while migration is
supported. Deprecation guidance must identify the replacement, explain the
semantic difference, warn without blocking ordinary conversational language,
and specify the removal condition.

## Reporting

Report the two domains separately:

```text
Intents: captured, researching, refining, planned, deferred, closed
Work items: Backlog, Ready, Active, Blocked, Review, Done, Deferred
Research: new references, needs review, linked references
```

Never describe a closed intent as a “done backlog item.”
