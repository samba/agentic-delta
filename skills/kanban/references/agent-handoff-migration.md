# Agent Handoff Migration

There is no persisted legacy handoff state. These instructions migrate agent
output behavior to the version-2 interchange document; the helper does not
accept legacy aliases.

## Required changes

- Add a stable `handoff_id`; retry the identical document with the same id.
- Replace skill or capability names with the assigned `specialist_class`, its
  integer `specialist_class_version`, the assigned `engagement_role`, and the
  producing `worker_id`. Do not infer a class from the skill that activated.
- Add `independent` as an explicit boolean.
- Replace compound results with separate fields:
  - `architecture-pass` becomes `gate_id: architecture`,
    `applicability: applicable`, `gate_recommendation: pass`, and
    `status: complete`;
  - `operational-ready` uses `gate_id: production-readiness` with the same pass
    tuple;
  - `release-clear` uses the selected security gate with the same pass tuple.
- Replace `applied` with `applicability: applicable`.
- Replace `skipped-not-applicable` with `applicability: not-applicable`,
  `gate_recommendation: not-applicable`, `status: not-applicable`, and a
  rationale finding.
- Represent `blocker`, `required-follow-up`, and `advisory` as finding
  severities, not overall gate results.
- Use only canonical rework stages: `Discover`, `Design`, `Implement`,
  `Verify`, `Deliver`, or `Observe`.
- Emit structured source, artifact, finding, evidence, risk, and decision
  objects matching `specialist-handoff.schema.json`; arbitrary strings are not
  accepted in those arrays.

## Submission

```bash
python3 skills/kanban/scripts/kanban.py handoff validate handoff.json \
  --expected-task <task-id> --expected-run <run-id>

python3 skills/kanban/scripts/kanban.py handoff ingest handoff.json \
  --expected-task <task-id> --expected-run <run-id>
```

Validation proves document and current-context conformance. Only a committed
ingestion receipt proves acceptance. If a retry reports an existing receipt,
use it; if the same `handoff_id` has different content, stop and issue a new id
only after determining which attempt is authoritative.

## Default-review posture

Agents migrating from coordinator-selected or version-11 comprehensive review
must first create a task work profile and version-13 review/guidance plan. Dispatch every
pending plan item with its stored class context, `review_purpose`, and
`review_plan_item_id`. Assurance uses `inform`; control uses independent
`review`. Return substantive evidence or the canonical `not-applicable` tuple
with a rationale finding tied to examined scope. Only ingestion of the matching
handoff resolves a reviewer-determined item.

There are no supported live legacy states, so the schema does not infer work
types or convert old gate requirements. For unfinished work, preserve old
records as history, profile the current scope, create a new review plan, and
drain it. Do not rewrite completed gates; create a new plan when completed work
must be evaluated under the assurance/control standard.

## Assurance obligations

Assurance producers should add an `obligations` array when a material finding
must change downstream production. Each item names its frozen `tenet_id`, stable
`obligation_id`, type, summary, lifecycle stage, verification method, owner, and
optional affected artifact. Do not place obligations in control handoffs.

Agents migrating from consultation-only assurance must translate every material
finding into an obligation or record an attributable disposition through the
coordinator. A passing assurance handoff does not by itself make a task
pullable when required guidance remains unresolved.

## Principle and tenet migration

On schema initialization, each legacy `principles` row receives a project-local
version 1 without changing its statement. Agents must then review its intended
outcome, authority class, rationale, and source links; migration does not invent
those facts. New behavior belongs in a tenet linked to one or more principles,
not in opaque principle JSON.

For unfinished governed work, create a fresh work profile and review plan. This
freezes a version-13 guidance snapshot. Do not manufacture snapshots for
completed historical work. Draft experimental tenets remain inactive globally;
start an experiment, assign a task before plan creation, and let its snapshot
pin the assigned baseline or variant.

## Schema 14 project enrollment and bugs

Initialization enrolls every active specialist class in each unfinished legacy
intent with status `enrolled`; it does not invent a completed consultation,
guidance proposal, codebase finding, or bug assessment. Agents should conduct
early consultations for active projects and retain explicit not-applicable
results where appropriate.

New handoffs may include `guidance_proposals`. Migrate free-form project rules
into proposals first, then separately adopt and version them; do not treat old
notes as governing principles or tenets automatically. Legacy defect notes
should be registered as bugs with their original observation, expectation,
evidence, and reporter where known. Specialist assessments and priority must be
performed under the current project goal rather than inferred from old labels.

A principle proposal states a durable outcome and leaves
`verification_strategy` null. A tenet proposal states actionable work and a
non-empty verification strategy. Neither becomes governing merely because the
handoff was accepted. Control handoffs cannot propose guidance; use early
consultation or assurance.
