# Board Walk

Use this workflow when the user says `walk the board`, asks for work status/progress, asks what to start next, or asks to backfill work.

## Sequence

1. Review work pending acceptance.
   - Inspect all cards in the project-declared review column, usually `Review`.
   - Verify completion payload: commit hash or no-commit reason, changed files, validation evidence, and simplicity/idempotency/error-boundary check.
   - Task workers with missing validation, review fixes, or narrow refinement work before accepting completion.
   - Ask clarifying questions only when they block acceptance or materially change completion criteria.
   - Move satisfactory cards to the declared completed state, usually `Done`, through allowed transitions.

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

4. Backfill Ready.
   - Treat `backfill_goal Ready` as the target number of Ready cards.
   - If Ready is below target, interview across Backlog and unclear cards.
   - Each interview round should ask the 3 broadest-impact questions across the whole backlog and the 3 deepest-impact questions for the most-ready backlog tasks.
   - Before asking, inspect current code, docs, tests, and board context to infer answers where confidence is high.
   - Apply user answers across all relevant backlog tasks, refine scope/success criteria/constraints/plans, re-estimate confidence/readiness/complexity/ambiguity, and promote tasks that reach the readiness threshold.
   - Continue until Ready reaches its target or no more useful clarification can be asked without new research.

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

Keep `Blocked` and `Review` as first-class work. Do not hide validation debt in `Done`; create or retain a validation card when proof remains deferred.
