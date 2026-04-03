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
- Tag each event to a context track so raw evidence and derived method lessons stay partitioned.
- Include feedback and checkpoint linkage (for example commit refs/ranges, validation checkpoints).
- Include a short reason summary for each material delta so later review can reconstruct why a change happened without replaying the full thread.
- Retain raw logs for 7 days by default.
- Rotate daily and compress older daily artifacts.
- Produce weekly aggregates by default.
- Keep both:
  - high-level summaries, and
  - dense-context summaries suitable for diagnosis and method learning.
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
6. Rotate daily logs and compress previous day artifacts.
7. Enforce retention pruning at 7-day default horizon.
8. Build weekly aggregate artifacts with:
   - high-level outcomes/trends,
   - dense-context chains (feedback -> decision -> checkpoint -> outcome).
9. Expose query paths by time window, checkpoint range, and context track.

## Required Deliverables

- Schema definition and usage guidance.
- Track-partition guidance covering execution vs reflection records.
- Leakage-audit guidance for promoted method deltas.
- Rotation/compression/retention policy.
- Weekly aggregate template with dense-context sections.

## Reference Material

- Event schema template: [references/event-schema-template.md](references/event-schema-template.md)
