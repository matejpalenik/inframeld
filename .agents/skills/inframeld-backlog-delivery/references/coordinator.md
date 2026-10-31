# Finish independent work without expanding the project

Alice has several active branches, one shared integration stack and a limited review queue. The coordinator's job is to turn that work into useful merged capabilities. Opening more assignments helps only when they can progress independently and there is capacity to finish them.

## Establish the run

Setup, planning and rehearsal do not authorize delivery. For a native live launch, obtain the repository, finite issue snapshot, permitted Git/GitHub operations, internal messaging and merge policy from the actual human request. Preserve paid-call and production restrictions. Create only the explicitly requested coordinator Goal, with no invented token budget. Separate-chat mechanics remain in the personal adapter.

Default native scope is the launch-time open implementation snapshot in `matejpalenik/inframeld`, milestone 1 (`v1`). Exclude Studio and aggregate epics. Later issues need authorization. Reconcile already delivered work from actual merged evidence. A closed specification issue does not prove an implemented prerequisite exists.

Use `pnpm delivery:plan` for the GitHub snapshot and dependency candidates. Inspect issue acceptance, native blockers, open PRs, unpublished work and likely contracts before assignment. The helper cannot establish code independence. Missing decisions block dependent work, while unrelated authorized work may proceed.

Use the [assignment brief](assignment-protocol.md#use-one-short-assignment-brief). Clear ownership once. Request independent plan review for material architecture, authorization, public-contract, persistence, shared-harness changes or a newly proposed cross-issue boundary. A routine implementation within accepted patterns needs a proportionate scope check and later independent implementation review, not another extensive planning ceremony.

For a material plan, seek roughly 9/10 on the relevant quality rubrics and at most 2/10 overengineering risk, where lower risk is better. Review the complete proposed capability, including verification infrastructure. If material gaps prevent those targets, reconsider the scope or approach before dependent implementation. Explain the actual gap and smallest remedy rather than requesting a preferred score. Implementation-only evidence is N/A at planning time. These are design targets, not new numerical merge gates or reasons to polish optional details indefinitely.

### Review a newly discovered dependency

Use [defect triage](discovered-defects.md) when the discovery is a bug or tooling problem. Decide whether it belongs to the feature, is a genuine verification prerequisite, or can be recorded for later. The coordinator owns authorized issue publication and checks for duplicates. Recording a defect and authorizing its implementation are separate decisions.

Before absorbing another feature, state the accepted behavior that cannot be implemented or verified, missing evidence, owning issue and exact unblock condition. Sharing an authentication topic is not itself a dependency.

Compare an existing supported capability or procedure, an appropriate test fixture, a small supporting PR and serial prerequisite delivery. A fixture can test a consumer's handling of supplied evidence. It cannot qualify a promised real provider or operator journey. Independently review a proposed split or integrated boundary against acceptance and check for cycles. Resolve required findings through Review. Conditional documentation cannot replace promised behavior.

For example, Project metadata resolution may be independently testable, while an approved human repair journey also needs a real transient proof producer. Confirm which capability a PR promises before making the entire account UI a gate. If the promised repair cannot work without the producer, keep that part blocked or accept an explicit supporting boundary. Never silently weaken acceptance.

Record the chosen boundary and remaining work in the brief. Routine sequencing inside authorization needs coordinator alignment. A changed accepted contract or expanded authority still needs the owning human decision. Useful supporting PRs follow [their merge gates](gates-and-recovery.md#merge-useful-prerequisites-without-closing-the-feature).

## Choose parallel or serial delivery deliberately

| Observed relationship | Schedule |
| --- | --- |
| Independent behavior, paths and resources | Implement in parallel. |
| Independent code sharing the fixed integration stack | Implement in parallel and execute integration serially. |
| Same public contract or authorization rule | Agree the contract and one owner before dependent edits. |
| Shared migration order, lockfile, generated clients or common CLI infrastructure | Give the shared change one writer and usually sequence delivery. |
| A feature consumes an unfinished prerequisite | Prefer a small qualified prerequisite PR, then continue from main. |
| Material overlap or unknown ownership | Pause affected writes and deliver serially until reconciled. |

Textually separate files do not prove semantic compatibility. Conversely, a shared integration queue does not justify blocking unrelated unit checks, documentation or code review. Avoid long stacks of unmerged feature branches when a smaller prerequisite can land first. When a stack is necessary, record its actual bases, merge order and requalification boundary.

Native maxima remain ten workers, two code reviewers, one DX reviewer and one documentation writer, subject to actual runtime capacity. These are ceilings. Start with the independent work the run can finish, often two or three implementations, and expand only when review and integration queues permit it. Keep specialist capacity available. Do not reserve four specialists permanently for every issue or change the selected model to fill slots.

On specialist reuse, send a fresh issue-specific brief without the previous assignment's assumptions or a desired verdict. Prefer a fresh review context when supported. Count still-open agents against the runtime limit until actually released. Reuse a verified idle worker rather than accumulating replacements. Temporary model unavailability needs bounded backoff and lower dispatch pressure, not silent model substitution.

## Prioritize completion when the run is overloaded

When several branches wait on the same prerequisite, review queues grow, or harness work dominates feature progress, stop opening new implementation assignments at a safe checkpoint. This pauses dispatch, not the Goal or a running command. Preserve current work and let safe operations finish.

List active capabilities, reviewed checkpoints, real blockers and the next useful merge. Finish one coherent prerequisite or ready capability at a time through review, required checks and merge. Independent workers may still perform already assigned private checks, documentation and review. Keep truly blocked work parked. Resume new dispatch once ownership is reconciled and the integration/review queue can finish another independent assignment. No arbitrary waiting period or permanent serial-only mode is needed.

Prioritize a narrowly scoped shared maintenance PR when it genuinely unlocks several qualified branches. Do not bypass hooks, weaken cleanup or add another execution framework to avoid that blocker. Review any expansion of the maintenance scope under [Testing's harness boundary](../../inframeld-testing/references/isolation-and-evidence.md#keep-harness-repairs-bounded).

Name the next useful PR and what still prevents it. If correction attempts create further infrastructure work while the same acceptance case fails, reassess the whole repair rather than approve only its next small patch. The [#237 case](case-237-testing-repair.md) illustrates why separate worktrees and scoped review scores alone do not establish progress.

### Park blocked work and reuse its worker

Preserve a recoverable checkpoint in the existing worktree with the exact blocker, next action and unblock condition. Obtain a positive writer-stop acknowledgment and reconcile all held resources. In native mode, `retire` releases the unfinished assignment only after verified cleanup. Retirement is not feature completion. Never delete a branch or discard dirty work to make room.

Recheck the finite snapshot for a verified independent assignment, then give the released worker a fresh worktree and brief. Resume parked work through `adopt` after checking intervening main and contracts. If no independent work is verified, report that reason. Do not invent cleanup projects to keep agents busy.

## Own coordination, not every command

The coordinator is the sole run-state writer and shared-resource allocator. Use [existing helpers](../../../../scripts/delivery/README.md) in native mode. `plan` and `status` inspect, `init` and `apply` record state, and assessment commands assess supplied observations. None dispatches workers, grants authority or merges. Atomic persistence and expected revisions do not make competing coordinators safe.

Record ownership before dispatch. Shared outputs need one writer or an acknowledged handoff. `amend`, `revise`, `adopt` and `retire` keep their implemented validation and evidence-invalidation rules. Reconcile actual writers and resources before changing ownership. A recorded merge alone does not release an assignment.

Grant a complete maintained integration operation to one executor under the [resource policy](gates-and-recovery.md#shared-resources-are-observed-ownership). Workers choose routine edits and isolated checks inside their brief. Avoid relaying every subprocess or creating a new permission receipt for each private formatter or test.

Use short event messages for changed ownership, blocked decisions, review requests, integration needs, source changes and observed merges. Peer suggestions cannot revise authority. Return summaries and raw-log references rather than filling the main context with command transcripts.

## Merge, reconcile and measure

Follow [gates and recovery](gates-and-recovery.md), including current evidence, failure classification, serial expected-head merges and the host boundary. After an observed merge, notify affected workers of actual main and changed contracts. Rebase only at safe checkpoints and refresh affected evidence. Do not merge several PRs against stale main.

At meaningful checkpoints, report shipped capabilities, the next eligible PR, exact blockers and any human decision. Use existing observations to notice time to useful PR/merge, review/integration waiting, repeated checks without new evidence, harness versus feature work and avoidable approval requests. Do not build a metrics service or treat test, agent or receipt counts as delivery goals.

Three unsuccessful remediation cycles stop the affected issue under the owning failure policy. Host risk can stop affected runtime work sooner. Continue independent authorized work where safe. Complete the Goal only when the finite authorized outcome is actually delivered and reconciled. Time, usage or a helper's `ready` result cannot establish completion.
