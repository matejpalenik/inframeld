---
name: inframeld-review
description: Reviews Inframeld code, architecture and commit or merge readiness, prioritizing human maintainability and proportionate V1 engineering. Provides evidence-backed findings and ratings. Use for requested reviews, not behavior-only explanations or routine implementation.
---

# Review Inframeld for its next maintainer

Help the developer decide whether a change is understandable, correct and worth its maintenance cost. Assume they read much of the code but write less of it. Explain important findings through a concrete scenario and the smallest useful remedy.

For example, Alice runs the integration suite sequentially on her machine and in an isolated CI job. A new lease coordinator needs a demonstrated competing operation to justify its ownership records, recovery paths and tests. Separately, simultaneous production requests may require real transaction safeguards. One developer does not imply one production caller.

This skill owns the review process, scoring and report shape. [Coding Standards](../inframeld-coding-standards/SKILL.md), the affected language standards and domain contracts own the rules being assessed. Follow root and directory instructions. Review is read-only unless the user also requests changes. It grants no commit, push, PR comment, merge or issue-closing authority.

## Establish the review

Resolve the requested files, change, branch or PR first. For a normal review of the current work, include staged, unstaged and relevant untracked files. Do not silently choose a Git base or rate unrelated repository code. For a repeated review, recheck the fixes and their affected callers, preserving the earlier scope unless new evidence requires expansion. State the scope and material omissions.

Identify the delivered user outcome, accepted constraints and invariants before judging the design. Read the actual implementation, its callers, tests and relevant owning guidance. Distinguish accepted contracts, pending proposals and delivered behavior. Ask only when missing scope or a material tradeoff cannot be resolved from the repository. A relevant pending decision can block dependent work, while an unrelated proposal cannot.

Load [Python Standards](../inframeld-python-standards/SKILL.md) for authored Python, [Rust Standards](../inframeld-rust-standards/SKILL.md) for authored Rust, and package guidance for other languages. Retain generator ownership for SDK changes. Read the owning domain workflow and required component references. Do not load every skill or impose Python architecture on Rust.

## Conduct the review

1. Follow one realistic success and the relevant failure path through inputs, validation, authority, decisions, effects and output. Check the boundaries where representations or owners change.
2. Apply the affected [review lenses](references/review-lenses.md). Prioritize human navigation, safe modification and present need. Check correctness, security, data integrity, tests, resource bounds, developer experience and operational behavior where the change touches them.
3. Challenge complexity with an actual supported scenario. Compare keeping, simplifying or deferring it. Explain which invariant a simplification must preserve. Do not reward minimum line count, abstraction count or reuse that hides different policies.
4. Gather proportionate evidence. Use existing checks and bounded local probes when permitted. Label fresh, cached, reported and unavailable results. Do not run the entire suite reflexively, edit tracked files, create another test stack or contact live services merely to produce a review.
5. Consolidate findings by root cause. Give each material finding a trigger, affected behavior, evidence, verified source location, severity and smallest recommendation. Separate demonstrated defects, well-supported inferences, unresolved evidence and optional preferences. Remove speculative findings and duplicate nits before reporting.

## Judge the tradeoffs

V1 supports one host with Docker Compose and a maintenance budget one developer can sustain. Evaluate scalability against supported workloads and name unmeasured assumptions. Preserve sensible ownership and replaceable boundaries for possible distributed/Kubernetes evolution, without requiring its controllers, queues, deployment files or plugin systems now. Never claim future distribution is already qualified.

Respect accepted risk decisions unless changed evidence invalidates their assumptions. Do not trade away authorization, data integrity or recovery correctness to lower complexity. Mandatory coding conventions still apply. A pattern preference alone is not a defect, and a passing test count is not a quality argument.

## Report the decision

Use [scoring and the standard report](references/scoring-and-report.md). Put findings before the scorecard, then give the scope, important tradeoffs, evidence and next actions. Show an overall quality judgment and category ratings out of ten. Overengineering risk uses the opposite direction and must be labelled explicitly. Use N/A or Not assessed rather than inventing scores.

Separate commit readiness from merge/issue-closure readiness under the [Definition of Done](../../../docs/development/definition-of-done.md). Pending final-revision CI alone does not make a coherent change unfit to commit. A severe defect cannot be averaged away by high ratings elsewhere.

When no material finding remains, say so within the reviewed scope and stop inventing work. Do not demand a refactor to reach a round score, increase ratings merely because a review was repeated, or present scoped review as exhaustive production certification.
