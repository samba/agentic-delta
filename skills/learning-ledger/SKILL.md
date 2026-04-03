---
name: learning-ledger
description: Use when the user asks to capture execution/feedback/checkpoint history for later reflection and method improvement. Maintains structured, rotated logs and dense-context aggregates for short retention windows.
---

# Learning Ledger

## Use This Skill When

Use this skill when the user asks to:

- log prompts/interactions with timestamps,
- record feedback-loop and checkpoint context (for example commits/tests/decisions),
- rotate/compress logs,
- retain short windows and build periodic aggregates for learning.

## Integration

This skill is part of an integrated method stack with:

- `delegator`: produces execution-lane and validation events worth recording.
- `adaptive-reflection`: consumes ledger artifacts to refine methods and skills.

Expected flow:

1. `delegator` executes and emits meaningful state transitions.
2. `learning-ledger` records those events and checkpoints in structured form.
3. `adaptive-reflection` uses the retained and aggregated evidence to improve methods.

## Core Policy Defaults

- Use structured event records (timestamped).
- Keep ledger artifacts project-local; do not store execution/reflection ledgers outside the active project scope.
- Record storage metadata on each artifact so project-local compliance can be validated from the schema, not inferred from convention.
- Tag each event to a context track so raw evidence and derived method lessons stay partitioned.
- Include feedback and checkpoint linkage (for example commit refs/ranges, validation checkpoints).
- Include a short reason summary for each material delta so later review can reconstruct why a change happened without replaying the full thread.
- Retain raw logs for 7 days by default.
- Rotate ledgers daily and run nightly compression for high-context daily artifacts.
- Produce 7-day aggregates by default and compress those aggregate artifacts.
- Keep tiered retention:
  - raw event logs: short horizon only,
  - compressed daily and compressed 7-day aggregates: medium horizon,
  - longitudinal snapshots: long horizon, redacted and trend-focused.
- Keep both:
  - high-level summaries, and
  - dense-context summaries suitable for diagnosis and method learning.
- Retain up to 4 compressed 7-day aggregate artifacts by default.
- Enforce a hard size limit of 1MB per compressed daily rotated ledger artifact.
- Enforce a hard size limit of 1MB per compressed 7-day aggregate artifact.
- When compaction is required for either daily or 7-day artifacts, record loss-accounting that states what detail was dropped, what signal was preserved, and why the retained summary still satisfies the intended use.
- Audit cross-track leakage before promoting a derived lesson into a reusable method artifact.

## Workflow

1. Define event schema and redaction rules.
2. Partition each event into the appropriate context track:
   - `execution`: concrete task flow, checkpoints, tests, commits.
   - `reflection`: distilled lessons, hypotheses, and method deltas.
3. Append structured events during execution and review loops, including a concise reason summary for meaningful redirects, fixes, and learned deltas.
4. When a reflection artifact derives from execution history, record an explicit linkage back to the source delta or checkpoint.
5. Run a leakage audit before promoting cross-track conclusions:
   - verify the reflection summary does not pull in unnecessary raw context,
   - verify the execution record retains the detailed evidence,
   - mark the audit result in the ledger event.
6. Rotate daily logs and run nightly compression of prior-day high-context daily ledgers.
6.5. Validate each compressed daily rotated ledger size is <= 1MB; if not, re-summarize for higher signal density and recompress until within limit.
6.6. When daily compaction occurs, append loss-accounting describing preserved signal, dropped detail, and compaction rationale.
7. Enforce retention pruning at 7-day default horizon.
8. Build 7-day aggregate artifacts with:
   - high-level outcomes/trends,
   - context-dense, high-signal chains (feedback -> decision -> checkpoint -> outcome),
   - explicit linkage back to compressed daily artifacts.
   - If an aggregate exceeds 1MB, iteratively compact with higher-density summarization until it fits while preserving high-signal context.
   - When 7-day compaction occurs, append loss-accounting describing preserved signal, dropped detail, and compaction rationale.
9. Produce periodic longitudinal snapshots that retain only redacted summaries, stable identifiers, and trend deltas for slow-burn analysis.
10. Extend the raw-retention window only when evidence is still too sparse or confidence is still too low to classify a pattern safely.
11. Compress each completed 7-day aggregate and retain only the most recent 4 compressed 7-day aggregates.
11.5. Validate each compressed 7-day aggregate size is <= 1MB before retention; if not, re-summarize and recompress until within limit.
12. Expose query paths by time window, checkpoint range, and context track.

## Required Deliverables

- Schema definition and usage guidance.
- Track-partition guidance covering execution vs reflection records.
- Leakage-audit guidance for promoted method deltas.
- Rotation/compression/retention policy.
- Tiered aggregate and longitudinal snapshot policy.
- Raw-retention extension triggers and bounds.
- Project-local storage guidance for ledgers and aggregates.
- Artifact storage metadata and compliance-check guidance.
- 7-day aggregate template with context-dense, high-signal sections and compression/retention rules (keep latest 4).
- Aggregate size-bound policy with 1MB hard cap and compaction fallback procedure.
- Compaction loss-accounting requirement for daily and 7-day artifacts.

## Reference Material

- Event schema template: [references/event-schema-template.md](references/event-schema-template.md)
