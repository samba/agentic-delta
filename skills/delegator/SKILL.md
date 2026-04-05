---
name: delegator
description: Use when the user marks work as delegated, background, queued, or parallelizable. Split the task into non-blocking worker lanes with concrete exit criteria, queue order, blocker handling, progress probing, research-first refinement, and final review before closure.
---

# Delegator

## Use This Skill When

Use this skill when the user describes work as delegated, background, or to be done later while other work continues. The goal is to turn one vague request into a queued set of concrete lanes that can be executed in parallel, monitored, and closed only after proof of completion.

## Integration

This skill is part of an integrated method stack with:

- `learning-ledger`: captures time-stamped interaction/checkpoint events for longitudinal learning.
- `adaptive-reflection`: converts evidence into method adjustments and skill deltas.

Expected flow:

1. `delegator` executes and coordinates work.
2. `learning-ledger` records relevant events and checkpoints.
3. `adaptive-reflection` analyzes results and refines methods.

## Operating Rules

- Prompt grammar:
  - `async <verb> <context>` means coordinate the action entirely in background lanes.
  - In `async` flow, foreground returns to planning and status only, not implementation.
- Mode control:
  - `enter delegator mode` enables strict enforcement: foreground stays planning-only and active implementation runs strictly in background lanes.
  - `exit delegator mode` allows foreground to resume active implementation focus.
- Per-prompt override while in delegator mode:
  - `active <verb> <context>` allows immediate foreground execution for that task.
  - After the active task completes, delegator mode remains the default.
- Interaction precedence:
  - In delegator mode, ambiguous execution requests default to background lanes unless explicitly prefixed `active`.
  - Status reporting and completion notifications remain unchanged.
- Do not execute delegated implementation work in the main thread.
- If no workers are available, queue delegated tasks and dispatch them to the next available worker.
- Keep delegated lanes running in the background while the foreground thread stays available for planning and prioritization.
- Do not block foreground planning on lane completion unless the next foreground decision strictly depends on that lane's result.
- Start with an initial research lane before implementation for delegated objectives.
- Use research to identify optimal solutions grounded in best-practice, open-source, and well-supported approaches before expanding implementation.
- Treat minimum complexity as both an entry criterion (for selecting a path) and an exit criterion (for accepting a result).
- Apply a two-pass design checkpoint when work crosses boundaries, changes shared orchestration or safety semantics, has high validation cost with ambiguity, shows recent churn or rework, or fans out to more than one consumer. Use the first pass to name the safest narrow path and the second pass to confirm the design before broad implementation.
- Skip the two-pass checkpoint for low-risk local work that stays within one owner, one consumer, and one validation surface, unless new risk appears during execution.
- Define the overall goal, risks, and exit criteria before starting implementation lanes.
- Split ambiguous scope into smaller subtasks with explicit ownership and non-blocking boundaries.
- Assign clear priority order for the queue.
- Keep at least one dedicated coordinator lane for progress checks, unblock handling, criteria refinement, and final review.
- Ask implementation lanes to propose concrete task paths against the current criteria.
- Let the coordinator aggressively refine those criteria and proposed paths using the discovered research, with the goal of minimizing solution complexity.
- If a lane is blocked, pause it, record the blocker, and move it to the blocker owner's queue as the next priority.
- Retask inactive workers with the next unblocked highest-priority item.
- Continue prompting active workers until their exit criteria are proven.
- Poll lane progress on a cadence, but keep polling non-blocking and resume foreground planning immediately between checks.
- If a lane is ambiguous, diagnose the goal, narrow the criteria, and research authoritative open-source or publicly documented solutions before adding complexity.
- For larger delegated lanes with code changes, require a draft commit when lane exit criteria are met; keep commits topic-scoped and non-final until integration review.
- When a group of lanes completes, review the aggregate against the larger goal, then queue any remaining gaps before closing the work.
- Report completion status to the user promptly whenever a lane meets exit criteria, including what finished and what remains.
- When a reflection backlog candidate is proposed from observed lane patterns, notify the user immediately with the candidate title, track (`project-context` or `abstract-method`), and evidence refs.
- Before dispatching validation work, evaluate whether any required test run is likely to exceed 30 seconds.
- If expensive validation (>30s expected) is needed, present the expected test path to the user for approval before execution.
- Do not execute unapproved expensive test runs in background workers.
- If an expensive run fails after a change intended to fix a known issue, immediately switch to diagnostic/research mode.
- Freeze further implementation changes that would require another expensive run.
- Before any further expensive run, require a confidence reset:
  1. extract failure evidence,
  2. re-rank hypotheses,
  3. research unresolved high-impact questions,
  4. define the smallest high-confidence delta,
  5. state the expected observable effect.
- Only then permit another expensive run.

## Status Command

When the user issues the brief prompt `work status`, return a full background-work report that includes:

- all active lanes,
- all queued lanes,
- all workers and current assignment/state,
- completion results for prior work.

For prior work, include test results and validation outcomes that have not already been reported in the preceding 10 minutes.
If a result was already reported within that window, summarize it briefly and avoid duplicate detail.
When possible, include commit hashes, changed-file scope, and pending blockers.


## Pattern Sensing and Reflection Loop

### Lane telemetry (required at each checkpoint)

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

### Pattern checkpoint trigger (mandatory)

Run a pattern checkpoint when any condition is true:

- one signature appears in `>= 2` lanes in the same objective,
- one lane has `>= 2` signatures,
- the same signature repeats across two queue cycles.

### Pattern checkpoint actions

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

### Reflection backlog derivation

For each pattern checkpoint, emit a record with:

- `pattern_signature`
- `evidence_refs` (lanes/tests/commits)
- `cost_impact` (time/churn/rework)
- `action_taken`
- `expected_effect`
- `next_validation_probe`

Then derive backlog candidates:

- `project-context` candidate (always)
- `abstract-method` candidate (conditional)

### Abstract-method candidate gate

Keep an abstract-method candidate only if all pass:

- portability: actionable after removing project nouns,
- evidence breadth: observed in `>= 2` independent tasks or queue cycles,
- leakage audit: no project-specific identifiers.

If any gate fails, reclassify to `project-context`.

### Closure additions

Before objective closure:

- all triggered pattern checkpoints must have action + probe result,
- unresolved high-severity signatures must be zero,
- abstract-method outputs must pass leakage audit or be reclassified.

## Complexity Routing

Score delegated work on four dimensions using 0..5 values:

- `structural`: file count, ownership spread, interface surface, and topology changes.
- `behavioral`: runtime behavior, state transitions, safety semantics, and operator-visible effects.
- `validation`: depth, cost, ambiguity, and proof burden of the required checks.
- `coordination`: blocker risk, lane coupling, shared write pressure, and queue complexity.

Use the initial weighted model:

`TotalScore = (0.35 * structural) + (0.30 * behavioral) + (0.20 * validation) + (0.15 * coordination)`

Route by intent:

- `0.00` to `< 1.50`: low rigor
- `1.50` to `< 2.75`: medium rigor
- `2.75` to `< 4.00`: high rigor
- `>= 4.00`: very-high rigor

Apply hard trigger overrides regardless of weighted score:

- any change that affects more than one consumer or integrator,
- any ownership-boundary crossing,
- any change to safety or failure semantics.

When a hard trigger applies, require at least high rigor and use the two-pass design checkpoint before broad implementation.

## Workflow

1. Restate the delegated goal in one sentence.
2. Open a research lane first to evaluate best-practice, open-source, well-supported options and select the minimum-complexity path.
3. Score the work with the weighted complexity model and check for hard trigger overrides.
3.5. Capture lane telemetry and derive pattern signatures.
4. Choose the coordination rigor from the score or override result.
5. Identify risks, dependencies, and the smallest safe lane splits.
6. Write concrete exit criteria for each lane, including a complexity limit.
7. Order lanes by dependency and unblock value.
8. Dispatch delegated lanes to workers only; if no workers are free, queue lanes for the next available worker.
9. Start the unblocked lanes first, then the coordinator lane.
10. Evaluate validation scope; if any required test is expected to run longer than 30 seconds, request user approval of that test path before lane execution proceeds.
11. Probe lane progress and proof of exit criteria.
12. Continue foreground planning while lanes run; only pause foreground when a decision is blocked on a lane output.
12.5. When a pattern checkpoint yields backlog candidates, notify the user immediately with track and evidence refs.
13. Requeue blocked lanes behind the work that unblocks them.
14. For each completed larger implementation lane, create a draft commit before closure.
15. Notify the user promptly when each lane completes, with remaining queue state.
16. When all criteria are satisfied, run a final review and close the queue.

## Reference Material

For the detailed lane template, blocker handling rules, and worker coordination checklist, see [delegator-workflow.md](references/delegator-workflow.md).
