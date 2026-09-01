# Project Specialists, Existing-Work Review, and Bugs

Read this reference when starting a project, reviewing an existing codebase,
proposing project guidance, or registering and prioritizing a discovered bug.

## Early specialist enrollment

Capturing a project goal enrolls every active specialist class. Enrollment does
not force immediate serial review; it creates a durable obligation to obtain an
early project-context contribution or explicit not-applicable disposition.

Early consultation should examine the goal, constraints, known environment,
existing work, and authoritative sources. A specialist may propose:

- a **principle** when the project needs a durable outcome-oriented governing
  belief; or
- a **tenet** when agents need actionable, scoped standard work with a
  verification strategy.

Return proposals through the handoff `guidance_proposals` array. Proposals do
not govern work automatically. The coordinator compares overlap and conflicts,
obtains material human decisions, stores accepted principles or tenets through
their versioned commands, and then links the proposal to the adopted record.
Rejected proposals retain rationale and an attributable decision.

Consult specialists early enough that accepted tenets can enter the first
guidance snapshots. Re-consult when the goal, architecture, environment, trust
boundary, operating model, or other relevant premise changes.

## Existing codebase review

A request to review an existing codebase starts an
`existing-codebase-review` task and freezes the normal all-specialist assurance
and control plan. Each specialist compares observed artifacts with:

- the project goal and success criteria;
- effective principles and tenets;
- known quality attributes and operational expectations;
- established solutions and current authoritative guidance in its discipline.

Return concrete risks, deficiencies, strengths, evidence gaps, earliest repair
stage, and proposed follow-up work. Do not manufacture findings to justify a
specialist's participation; use an evidenced not-applicable disposition when
the examined scope has no material concern. Assurance can propose missing
project guidance and obligations. Control independently verifies the review
packet and its evidence.

## Bug lifecycle

Register a bug as soon as a credible discrepancy between observed and expected
behavior is discovered. Preserve summary, goal, observation, expectation,
reproduction, environment, evidence references, and reporter. Do not require a
complete diagnosis before capture.

Registration creates one pending assessment for every specialist enrolled in
the project. Each specialist records either:

- `applicable`, with goal impact, urgency, risk, rationale, and assessor; or
- `not-applicable`, with examined-scope rationale.

SQLite blocks prioritization until every disposition is complete. The
coordinator then prioritizes the bug among remaining work using project-goal
impact, user harm, risk, urgency, dependencies, constraint effects, cost of
delay, and specialist evidence. Specialist recommendations inform priority but
cannot set it independently or displace a human priority decision.

Actioning creates a linked backlog task with the selected rank, reproduction,
expected behavior, regression obligation, and earliest repair stage. The bug
can resolve only after that task is Done. Preserve deferred or rejected bugs
with rationale rather than deleting them.
