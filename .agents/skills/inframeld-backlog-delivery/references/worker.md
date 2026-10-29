# Deliver one assigned issue

Alice's worker owns a feature branch while other workers change independent areas. The worktree separates files, but shared contracts can still collide. Treat the coordinator's assignment as the boundary: one issue, one branch, named paths and contracts, a base revision, current acceptance and explicit permissions.

## Start from a bounded plan

Read repository and directory instructions, Coding Standards, affected language/package guidance and the owning domain workflow. Read mandatory component references before proposing affected architecture or code. Load Application Contracts for transport or execution boundaries and the relevant SDK skill for generated-client work. Testing guides strategy and evidence when those decisions arise. Do not load every skill for a small task.

Confirm the assigned worktree and base. Read the current issue, acceptance and blockers. Identify the user outcome, smallest coherent implementation, expected failure behavior, tests, user documentation and affected public contracts. Return this bounded plan to the coordinator. Resolve a material pending decision before dependent implementation. Routine choices within accepted scope do not require repeated approval.

Report overlap before editing unassigned paths or contracts. Different worktrees do not give permission to race on the lockfile, migration order, OpenAPI, generated SDKs or shared navigation. Ask the coordinator for a revised assignment or a serial handoff. Do not silently create another abstraction to avoid communication.

## Implement and verify proportionately

Follow the repository's behavioral test-first procedure. Establish only necessary public scaffolds, require the intended behavioral failure, implement the smallest behavior and refactor with focused tests green. Preserve mandatory conventions and valid exceptions. Do not add architecture-enforcement tests or speculative infrastructure.

Use local unit and fixture checks that fit the change. Request an exclusive resource grant before starting shared integration services, reserving ports or using a shared database or Compose project. Only the coordinator grants and records ownership. Do not infer a free resource from a quiet terminal, elapsed time or stale status.

For user-visible work, request the shared documentation writer with exact disjoint paths and the implementation revision. The writer uses the approved brief and page patterns without a repeated outline-approval loop. Shared navigation has one named owner. Review the returned page manifest and example evidence against the implementation. An internal-only change can explain why no user page changes are needed.

You are the issue's sole Git writer. Specialists never stage or commit your worktree. Wait for their file handoff, inspect the diff and ensure no concurrent edit is in progress before staging owned changes. Do not use broad add/reset/clean operations that capture or remove another agent's work. Git operations must stay within the future live launch's authorization.

## Request independent review

Send the coordinator the issue revision, actual base/head, implementation summary, acceptance evidence, owned paths, checks and remaining gaps. Request an independent code reviewer, and DX review when the task changes CLI/SDK setup, public behavior, output, recovery or examples. A backend-only change can carry an explicit DX applicability reason. Missing review is not a passing review.

Reviewers inspect the actual change and return findings with evidence. Address P0/P1 and required P2 findings. The human can explicitly accept a bounded P2 risk and follow-up. P3 suggestions are optional. Do not add a change merely to raise a score. After three unsuccessful remediation cycles on the issue, report the remaining root cause and stop dependent work for coordinator escalation.

Read the PR template before preparing the title and description. Describe the complete delivered behavior and actual evidence. Distinguish local execution, cached results, reported CI and pending checks. Do not mark unverified acceptance complete or close the issue for a partial foundation outside its accepted scope.

## Freeze the checked revision

Before final review and CI, stop all branch writes, including documentation edits and generation. Record the exact head, base and current issue revision. Any push, rebase or acceptance change makes affected receipts stale. Inform the coordinator immediately when the implementation changes.

In a future authorized live run, the worker can push and prepare/update the PR within the launch policy. Required GitHub checks and CodeRabbit must apply to the final head. Read their actual conclusions and comments, then request or perform authorized remediation. Neutral, queued, rate-limited, missing and unknown states remain pending when a required review is not completed. Do not manufacture a pass or trigger unrelated paid services.

The worker does not merge. Return a revision-bound ready-for-assessment report to the coordinator. The coordinator independently checks merge eligibility and acts only under the explicit live authorization.

## Rebase at a safe checkpoint

When notified of a merged main revision, acknowledge the exact revision and affected contracts. Finish or safely stop the current command and freeze writes before rebasing. Do not rebase while tests, generators or the documentation writer are mutating the worktree. Report a checkpoint to the coordinator, update from the agreed main revision and resolve conflicts within your ownership.

Recheck semantics after resolving textual conflicts. Regenerate owned artifacts through the supported pipeline, rerun affected checks and obtain new relevant reviews. A clean merge conflict resolution does not establish compatibility. Return the new head/base and invalidate prior evidence.

On interruption, report unfinished commands, dirty files and resource ownership. Preserve recoverable work. The coordinator reconciles before reassignment. Unknown cleanup remains occupied until actual inspection confirms the resource is released. Rehearsal assignments stop at inspection and proposed handoffs, with no implementation, push, PR or merge.
