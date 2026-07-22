# Board Walk

Use this workflow when the user says `walk the board`, `do kanban loop`, asks
for work status/progress, asks what to start next, or asks to backfill work.

`do kanban loop` means: walk the board, start any unblocked ready work that
passes WIP and readiness rules, execute needed review validation, independently
review completed work, persist lane transitions/evidence, refine the backlog,
and report work progress.

## Sequence

1. Review work pending acceptance.
   - Inspect all cards in the project-declared review column, usually `Review`.
   - By default, when the user says `walk the board`, start background review workers for pending Review cards that do not already have an active review worker. The review worker should independently inspect the completion payload, changed files, validation evidence, simplicity/idempotency/error-boundary fit, and whether the card should move to Done, need rework, or need more validation.
   - A Review card cannot move to `Done` until an independent critical review explicitly confirms that the work done meets the card objective, requirements, constraints, and acceptance criteria, and that the claimed validation proof is adequate for the card scope.
   - Implementation validation alone is not sufficient for `Review` -> `Done`; missing, stale, incomplete, or merely self-reported review evidence must leave the card in `Review`, return it to `Active` for bounded rework, or mark it as needing more validation.
   - Do not automatically start background review workers when the user says `requiring manual review`, `I want to review their results myself`, or equivalent language reserving review decisions to the user.
   - If a Review card is marked as needing manual review, escalate it to the user instead of delegating: summarize the decision point, ask only clarifying questions that affect acceptance or rework, and identify any expensive validation path that needs approval.
   - Verify completion payload: commit hash or no-commit reason, changed files, validation evidence, and simplicity/idempotency/error-boundary check.
   - Task workers with missing validation, review fixes, or narrow refinement work before accepting completion.
   - Ask clarifying questions only when they block acceptance or materially change completion criteria.
   - Move only independently reviewed and accepted cards to the declared completed state, usually `Done`, through allowed transitions.
   - Persist review state with helper commands: `task review start`, `task review accept`, and `task review rework`. Use `task event add` for additional audit notes rather than editing the SQLite database directly.

2. Resume in-progress work.
   - Inspect every `Active` card and active worker.
   - Ask questions needed to resume correctly.
   - Continue or retask each lane until it has a concrete next action, blocker, or validation path.

3. Backfill active work.
   - Run `config list`.
   - Treat `backfill_goal Active` as the target number of active worker lanes.
   - Treat `wip_limit Active` as the hard cap.
   - Pull Ready work only when readiness gates are satisfied and ownership boundaries are clean.
   - Preserve review-first discipline, already-started-work discipline, dependency order, and WSJF.
   - Persist blockers with `task blocker add` and `task blocker remove`. Prefer removing a specific blocker over broad or ambiguous "clear" language.

4. Backfill Ready.
   - Treat `backfill_goal Ready` as the target number of Ready cards.
   - If Ready is below target, interview across Backlog and unclear cards.
   - Each interview round should ask the 3 broadest-impact questions across the whole backlog and the 3 deepest-impact questions for the most-ready backlog tasks.
   - Before asking, inspect current code, docs, tests, and board context to infer answers where confidence is high.
   - Apply user answers across all relevant backlog tasks, refine scope/success criteria/constraints/plans, re-estimate confidence/readiness/complexity/ambiguity, and mark tasks ready only when they reach the readiness threshold.
   - Continue until Ready reaches its target or no more useful clarification can be asked without new research.

5. Refine the backlog.
   - After pending Review cards have review workers started or manual-review escalations recorded, and after Ready work has been pulled into Active where appropriate, run the `references/backlog-refinement.md` workflow as part of the default `walk the board` behavior.
   - Ask needful clarifying questions that improve backlog refinement, but first infer answers from code, docs, tests, board state, and existing principles when confidence is high.
   - Persist refinements to `.kanban/kanban.db`: split complex backlog records into smaller executable records, mark useful broad records as umbrella/context, record dependencies with `backlog dependency add`, and mark only items that satisfy readiness rules as ready.
   - Keep refinement behind review-first and WIP discipline: do not use backlog grooming to avoid closing Review, advancing Active work, or respecting WIP limits.
   - In the board-walk report, summarize refinement changes and identify the smallest next board operation that improves flow.

## Status Reports

For `work status`, `work progress`, or `progress`, include:

- project kanban configuration: columns, WIP limits, backfill goals, and backlog counts;
- board grouped by column;
- active lanes/cards;
- queued, blocked, or deferred lanes/cards;
- known workers and assignments when background work exists;
- blocking clarification questions near the top;
- non-blocking clarification questions after progress, with default assumptions;
- completion results, validation outcomes, and commit hashes not already reported recently.

## Interview Discipline

Ask fewer, higher-leverage questions. Prefer questions that clarify multiple cards, raise readiness for the nearest-ready tasks, or resolve a theme principle. Before asking, do a code/document/backlog review to avoid questions that can be answered with high confidence locally.

When the user answers, update all affected cards and backlog records, not only the card that caused the question.

## Movement Rules

Do not force state movement. Use project-declared transitions and required rules. If a needed transition does not exist, propose the workflow update and record the rule before moving cards.

Never move a card from `Review` to `Done` solely because its implementation worker reports success, tests pass, or validation output exists. The transition requires an independent critical review result that recommends acceptance and cites adequate proof against the task objective, requirements, constraints, and acceptance criteria.

Keep `Blocked` and `Review` as first-class work. Do not hide validation debt in `Done`; create or retain a validation card when proof remains deferred.
