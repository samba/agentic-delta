# Event Schema Template

## Core Fields

- `ts_utc`: ISO-8601 timestamp
- `session_id`: conversation/session identifier
- `turn_id`: monotonic turn index
- `role`: `user|assistant|worker`
- `event_type`: `prompt|response|feedback|decision|checkpoint|commit|test`
- `text`: redacted body or concise summary
- `reason_summary`: concise explanation of why this event or delta mattered
- `context_track`: `execution|reflection`
- `classification_basis`: short note describing why the event belongs to that track
- `feedback_tag`: `approve|correct|interrupt|revert|redirect|praise`
- `checkpoint_type`: `commit|test|plan|release`
- `checkpoint_ref`: commit hash, run id, or plan checkpoint id
- `checkpoint_range`: optional commit range (`start..end`)
- `delta_link_id`: optional pointer linking a reflection delta back to its originating execution event or checkpoint
- `leakage_audit_result`: `not_applicable|pass|needs_review|fail`
- `outcome_tag`: `accepted|reworked|reverted|blocked|deferred`
- `lane_id`: optional worker lane id

## Aggregation Requirements

- Weekly summaries must include:
  - high-level trend summary
  - dense-context chain summary linking feedback, decisions, checkpoints, and outcomes
  - track-aware summaries that keep execution evidence and reflection deltas partitioned unless an explicit linked promotion is recorded
