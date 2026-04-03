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
- `storage_scope`: `project-local|cross-project|external|unknown`
- `storage_location`: project-relative path or project-scoped artifact locator; absolute or external paths are invalid
- `storage_compliance_result`: `pass|needs_review|fail`
- `outcome_tag`: `accepted|reworked|reverted|blocked|deferred`
- `lane_id`: optional worker lane id

## Aggregation Requirements

- Ledger and aggregate artifacts must remain project-local.
- Each record must include `storage_scope`, `storage_location`, and `storage_compliance_result` so local-storage compliance can be validated from the artifact metadata.
- Compliance check: fail if `storage_location` is absolute, outside the active project scope, or otherwise not project-relative.
- Each compressed daily rotated ledger artifact must be <= 1MB; when over limit, re-summarize for higher signal density and recompress until within bound.
- 7-day summaries must include:
  - high-level trend summary
  - context-dense, high-signal chain summary linking feedback, decisions, checkpoints, and outcomes
  - track-aware summaries that keep execution evidence and reflection deltas partitioned unless an explicit linked promotion is recorded
- 7-day aggregate artifacts should be compressed after creation, with retention limited to the latest 4.
- Each compressed 7-day aggregate must be <= 1MB; when over limit, re-summarize for higher signal density and recompress until within bound.
