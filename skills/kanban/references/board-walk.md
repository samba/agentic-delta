# Board Walk

Use this workflow when the user says `walk board`, `work status`, `review
completed work`, `close completed work`, `refine backlog`, `prepare next work`,
asks for work status/progress, asks what to start next, or asks to backfill
work.

Always read `references/commands.md` first. Deprecated workflow phrases must
warn and stop before this workflow starts.

`walk board` and the conversational alias `walk the board` mean: run one
bounded board-maintenance pass, then report. Inspect
Review, Active, Ready, Blocked, and Backlog; start only low-risk review,
refinement, or status lanes needed for board maintenance. Do not queue-drain
implementation work.

`work status` means: report current board state, active/background lanes,
blockers, validation debt, review items, and next pullable work. Do not start
new work.

For software-development objectives, use `references/autonomous-loop.md` as the
stage model inside the flow. The coordinator may sequence stage agents, but each
stage must run and record its own applicability, skip, blocked, or rework
decision before the next stage receives the task.

`prepare next work` means: fill or refine the Ready queue through clarification,
splitting, research, dependency mapping, and readiness validation. Do not
implement unless the user also gives an execution command.

## Sequence

1. Review work pending acceptance.
   - Inspect all cards in the project-declared review column, usually `Review`.
   - By default, when the user says `walk board`, `walk the board`, or `review completed work`, start background review workers for pending Review cards that do not already have an active review worker. The review worker should independently inspect the completion payload, changed files, validation evidence, simplicity/idempotency/error-boundary fit, and whether the card should move to Done, need rework, or need more validation.
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
   - After pending Review cards have review workers started or manual-review escalations recorded, and after Ready work has been pulled into Active where appropriate, run the `references/backlog-refinement.md` workflow as part of the default `walk board`, `refine backlog`, or `prepare next work` behavior.
   - Treat refinement as background work when execution capacity allows. The refinement lane should not block foreground status or review work unless a decision is required before implementation can proceed safely.
   - Ask needful clarifying questions that improve backlog refinement, but first infer answers from code, docs, tests, board state, and existing principles when confidence is high.
   - Map concrete integration paths for vague cards before they become implementation work. Identify producer, transport, persistence, runtime handoff, consumer, validation surface, and failure behavior.
   - When local context is insufficient, perform needful research early enough to compare concrete options and avoid avoidable rework.
   - Persist decisions, rejected alternatives, assumptions, and downstream implications in backlog notes or revised summaries so the human can review the reasoning before implementation relies on it.
   - Persist refinements to `.kanban/kanban.db`: split complex intents into smaller executable work items, retain useful broad intents as context, link work items to intents, record dependencies, and mark only items that satisfy readiness rules as ready.
   - Keep refinement behind review-first and WIP discipline: do not use backlog grooming to avoid closing Review, advancing Active work, or respecting WIP limits.
   - Include registered bugs in the same priority field as planned work. Obtain
     every enrolled specialist disposition before final rank; compare goal
     impact, user harm, urgency, risk, dependencies, constraint effects, and
     cost of delay rather than maintaining a disconnected defect queue.
   - In the board-walk report, summarize refinement changes, decisions captured for review, and identify the smallest next board operation that improves flow.

6. Continue only when requested by an execution command.
   - `walk board`, `work status`, `review completed work`, `close completed
     work`, `refine backlog`, and `prepare next work` are not autonomous
     queue-drain commands.
   - During `run workstream` or an approved `map workstream` followed by an
     execution command, automatically start background work for the
     highest-priority unblocked cards and planned intents that satisfy WIP,
     readiness, research-first, ownership, and validation rules. Include
     research tasks as viable work when research is the readiness gate for later
     implementation.
   - For software-development implementation work, require the autonomous loop
     stage artifacts before pulling implementation: goal contract, research
     brief when needed, design packet, design-validation record, and validation
     strategy. A trivial task may carry skip records from individual stages, but
     the stages still run.
   - Continue background refinement after each closure or newly unblocked
     dependency so unclear records are decomposed, researched, and made ready
     before the next implementation lane consumes them.
   - Convert newly clarified intents into Ready or Active work only
     when the required scope, success criteria, constraints, implementation
     plan, and validation proof are concrete enough for the card type.
   - Stop only when the queue contains no unblocked pullable work, the user
     pauses the flow, or remaining work is explicitly manual-review-only,
     externally blocked, permission-gated, or categorically deferred by the
     user.
   - Do not reinterpret a categorical deferral as permission to resume work.
     Resume deferred themes, validation modes, or risk classes only when the
     user explicitly lifts that deferral.
   - Keep reporting progress with active lanes, closures, proof, queued next
     work, stage applicability/skip records when material, rework routing, and
     the exact reason any remaining work is not pullable.
   - When mapping a workstream, report the proposed sequence,
     parallel lane groups, dependency order, research decisions to be made,
     validation gates, explicit exclusions, approval needed to proceed, and the
     board records where decisions/evidence will be persisted for human review.

## Status Reports

For `work status`, `work progress`, or `progress`, include:

- project kanban configuration: columns, WIP limits, backfill goals, intent counts, and work-item counts;
- board grouped by column;
- active lanes/cards;
- queued, blocked, or deferred lanes/cards;
- known workers and assignments when background work exists;
- blocking clarification questions near the top;
- open human decisions near the top, with their linked intent/task, options,
  recommendation/default, impact of delay, and safe work continuing;
- non-blocking clarification questions after progress, with default assumptions;
- completion results, validation outcomes, and commit hashes not already reported recently.

## Interview Discipline

Ask fewer, higher-leverage questions. Prefer questions that clarify multiple cards, raise readiness for the nearest-ready tasks, or resolve a theme principle. Before asking, do a code/document/backlog review to avoid questions that can be answered with high confidence locally.

When the user answers, update all affected intents and work items, not only the record that caused the question.

## Movement Rules

Do not force state movement. Use project-declared transitions and required rules. If a needed transition does not exist, propose the workflow update and record the rule before moving cards.

Never move a card from `Review` to `Done` solely because its implementation worker reports success, tests pass, or validation output exists. The transition requires an independent critical review result that recommends acceptance and cites adequate proof against the task objective, requirements, constraints, and acceptance criteria.

Keep `Blocked` and `Review` as first-class work. Do not hide validation debt in `Done`; create or retain a validation card when proof remains deferred.
