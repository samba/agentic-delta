# Delegator Workflow

## Queue Model

Use a queue of lanes rather than a single monolithic task when work can be split safely.

### Lane types
- `coordinator`: owns progress probing, criteria refinement, risk tracking, pattern checkpoints, and final review.
- `research`: owns authoritative documentation/source review and candidate-solution discovery.
- `implementation`: owns a disjoint file/path or feature slice.
- `validation`: owns tests and proof gathering for one lane.

## Startup Sequence

When a task is first delegated:
1. create the coordinator lane
2. start one research lane if the task is ambiguous, design-heavy, or unfamiliar
3. have implementation lanes propose candidate paths only after the research lane surfaces proven options
4. let the coordinator tighten criteria and reduce complexity before broad implementation begins

## Lane Contract

Each lane must have:
- explicit file or scope ownership
- concrete exit criteria
- known risks to mitigate
- required validation
- telemetry updates at checkpoint boundaries
- completion output: changed files, tests run, proof of exit criteria, and for larger implementation lanes a topic-scoped draft commit hash

## Telemetry and Pattern Signatures

### Required lane telemetry
- `replan_count`: number of scope/criteria changes.
- `blocker_count`: number of blocker events.
- `blocker_age_max_min`: max blocker age in minutes.
- `rework_count`: reverted or redone changes.
- `validation_fail_count`: failed validation attempts.
- `validation_ambiguous_count`: validations that did not prove outcomes clearly.
- `handoff_count`: lane ownership transitions.
- `user_correction_count`: explicit user corrections/redirects.

### Derived pattern signatures
- `SCOPE_THRASH`: `replan_count >= 2`
- `BLOCKER_RECUR`: `blocker_count >= 2` or `blocker_age_max_min > 30`
- `REWORK_LOOP`: `rework_count >= 1` and `validation_fail_count >= 1`
- `PROOF_AMBIGUITY`: `validation_ambiguous_count >= 2`
- `COORD_OVERHEAD`: `handoff_count >= 3`
- `GUIDANCE_MISMATCH`: `user_correction_count >= 2` in the same objective

## Pattern Checkpoint

### Trigger rules (mandatory)
Run a pattern checkpoint when any condition is true:
- one signature appears in `>= 2` lanes in the same objective,
- one lane has `>= 2` signatures,
- the same signature repeats across two queue cycles.

### Checkpoint flow
1. Pause starting new implementation lanes.
2. Classify root cause:
   - criteria ambiguity,
   - ownership-boundary mismatch,
   - validation design gap,
   - over-complex implementation path.
3. Choose one action:
   - `CHANGE_PATTERN` (simplify or reroute execution),
   - `APPLY_ANALOG_TOOL` (use a proven method/tool from similar prior context).
4. Define one next validation probe and resume execution.

## Reflection Backlog Derivation

For each pattern checkpoint, record:
- `pattern_signature`
- `evidence_refs` (lanes/tests/commits)
- `cost_impact` (time/churn/rework)
- `action_taken`
- `expected_effect`
- `next_validation_probe`

Then derive candidates:
- `project-context` candidate (always)
- `abstract-method` candidate (conditional)

### Abstract-method gate
Keep an `abstract-method` candidate only if all pass:
- portability: actionable after removing project nouns,
- evidence breadth: observed in `>= 2` independent tasks or queue cycles,
- leakage audit: no project-specific identifiers.

If any gate fails, reclassify to `project-context`.

### User notification rule
When a reflection backlog candidate is proposed, notify the user immediately with:
- candidate title
- track (`project-context` or `abstract-method`)
- evidence refs

## Prioritization

Order lanes by:
1. unblockers
2. ownership-boundary fixes
3. correctness/security fixes
4. feature work
5. cleanup and documentation

## Blockers

When a lane is blocked:
- pause it immediately
- record the blocker and unblock condition
- enqueue the lane behind the blocker owner’s next priority item
- resume it as soon as the blocker clears

## Ambiguity Handling

If a lane is unclear:
- reduce the scope into smaller measurable subtasks
- identify which proof point would distinguish success from failure
- research authoritative public sources or upstream code before inventing new machinery
- have the coordinator refine the acceptance criteria and candidate path before more implementation is started
- prefer the simplest viable solution that preserves existing behavior

## Coordinator Duties

The coordinator lane must:
- check worker progress regularly
- confirm exit criteria with artifacts, logs, or tests
- restart inactive workers on the next unblocked task
- re-evaluate the queue when a new proof point appears
- revise criteria when research reveals a simpler or more proven implementation path
- enforce draft-commit creation for larger completed implementation lanes before closure
- ensure pattern checkpoint records and probes are complete when triggers fired
- perform final review before closure

## Closure Gates

Before objective closure:
- all triggered pattern checkpoints must have action + probe result,
- unresolved high-severity signatures must be zero,
- abstract-method outputs must pass leakage audit or be reclassified.

## Lane Prompt Template

Use this structure when spawning a lane:

```text
Owner scope:
- <allowed paths>
- <disallowed paths>

Goal:
- <one concrete objective>

Exit criteria:
1) <deliverable condition>
2) <test condition>
3) <commit condition>
4) report: commit hash, files changed, tests run

Style constraints:
- minimal changes
- flat/shallow logic
- keep behavior stable unless task requires change
```

## Failure Handling

- If lane output violates ownership scope: reject and re-run with narrowed instructions.
- If lane cannot complete full scope safely: accept a bounded fallback slice only when exit criteria are rewritten and met.
- If tests conflict across lanes: serialize final integration in the coordinator and re-run merged validation.

## Suggested Lane Prompt

Use this framing for background workers:

> Work only within the assigned scope. Keep control flow simple and idempotent. Prefer the lowest safe error boundary. Report concrete exit criteria, blockers, proof of completion, candidate implementation paths, telemetry updates, and research-backed recommendations.
