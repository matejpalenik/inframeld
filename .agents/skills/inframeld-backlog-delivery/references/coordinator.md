# Finish existing issues before opening new work

Alice has a member-list PR merged, membership changes still unfinished and a new group feature available. She finishes the membership issue before replacing it with the new feature. A useful supporting merge advances the owning issue but does not release its finishing owner.

## Establish the run

Setup, planning and rehearsal do not authorize delivery. For a native live launch, obtain the repository, finite issue snapshot, permitted Git/GitHub operations, internal messaging and merge policy from the actual human request. Preserve paid-call and production restrictions. Create only the explicitly requested coordinator Goal, with no invented token budget. Separate-chat mechanics remain in the personal adapter.

When a later trusted human instruction explicitly resolves or replaces an earlier approval request, post an ordinary coordinator chat update identifying both messages by link, message ID or clear quoted context and stating what is resolved or superseded. The chat transcript is this record. Append a correction if the status changes, without adding a ledger or run-state field. The referenced human instruction remains the authority, not the coordinator's summary. If the client cannot dismiss the old question, make its superseded status clear in that update. Silence, elapsed time, peer advice and a generic continuation do not automatically erase a specific stop condition. Preserve all restrictions the later instruction did not change. If a delayed answer arrives after the PR merged under valid subsequent authority, explain that no additional cycle starts. The late answer supplies no retroactive justification for an unauthorized action.

Default native scope is the launch-time open implementation snapshot in `matejpalenik/inframeld`, milestone 1 (`v1`). Exclude Studio and aggregate epics from worker assignments. Use epic relationships to guide selection within that finite scope. Later implementation issues need authorization. Reconcile already delivered work from actual merged evidence. A closed specification issue does not prove an implemented prerequisite exists.

A live run needs actual authority to create, update and link qualification issues for human-facing features in its finite scope. Reuse existing human authorization without asking again for each ticket. Without publication authority, retain a draft and report the gap before the required handoff. Qualification tracking does not add an implementation assignment to the allowlist. A missing implementation prerequisite outside that scope still needs the existing scope authorization.

Use `pnpm delivery:plan` for the GitHub snapshot and dependency candidates. Inspect issue acceptance, native blockers, open PRs, unpublished work and likely contracts before assignment. The helper cannot establish code independence. Missing decisions block dependent work, while existing independent assignments may proceed.

### Prefer epic completion without serializing the backlog

Select the next whole issue to close from the existing unfinished queue before opening a new feature. Include recoverable parked work whose prerequisites have arrived. Name one finishing owner, the remaining acceptance, the delivered product and verification capabilities, and the shared contracts the owner may change. Keep that owner accountable through observed merge and closure or an explicit handoff accepted by a new owner. Choose a focused epic from developer priorities and actual dependencies. Epics remain aggregate outcomes.

Existing work means active assignments and preserved checkpoints. A new issue has not been started, even when already authorized by the finite backlog. An initial launch with no existing work can select from that backlog. After verified closure, select the next authorized issue with the same priority for recoverable unfinished work.

Keep each lane on its selected issue until its full accepted scope is delivered and closure is verified. A supporting merge, local checkpoint, review queue or ordinary repair is not a reason to replace it with unrelated work. When a genuine blocker prevents completion, preserve the checkpoint and name the missing capability, its owner and the return condition. Deliver its authorized prerequisite or resume another existing issue that can finish. Opening an unrelated new issue before that closure requires explicit human reprioritization. If no existing issue or prerequisite can advance safely, report the concrete blocker or decision and leave capacity unused.

Prefer one coherent PR. Split when the prerequisite is independently useful and reviewable, a required producer belongs to another owner, or separating a demonstrated repair materially reduces integration or recovery risk. Before the split, name the consumer, the evidence that will make the prerequisite usable, and the remaining path to the owning issue's closure. After a supporting merge, continue that path. Keep the finishing owner while delegating a prerequisite. A repeated supporting split needs a demonstrated obstacle to the next accepted behavior, not merely another separable component.

A component issue may close when its own accepted scope is delivered. Do not import the future consumer's entire journey into that issue. Keep a broader issue open when its own promised behavior is still missing. Apply the [supporting-PR gates](gates-and-recovery.md#merge-useful-prerequisites-without-closing-the-feature) and separate [human-work deferral](gates-and-recovery.md#separate-implementation-and-human-acceptance).

Parallelize existing issues and their necessary prerequisites only where contracts, review and integration capacity permit completion. Group related API changes when they form a coherent reviewable capability and avoid repeated generation. Let a qualified useful PR land without waiting for speculative batching, then return to its issue's remaining acceptance.

### Check prerequisites before assignment

Follow one concrete user operation before dispatching a writer. Identify the capabilities consumed by the promised behavior and its required checks, including any human journey. Record their owners and inspected delivery evidence in the existing [brief](assignment-protocol.md#use-one-short-assignment-brief):

| Prerequisite | Evidence needed before assignment |
| --- | --- |
| Behavior | The required producer/interface exists in the intended base with accepted semantics |
| Verification | The maintained verification route and its necessary real capabilities exist and can be executed under actual authorization |
| Human journey | The capabilities needed for the promised user experience are delivered, or that journey is explicitly outside an accepted component boundary |

Inspect relevant code/interfaces, merged PRs and scoped evidence. An approved design, an open implementation branch, a closed specification or a mocked response does not establish a delivered capability. This is a source/contract check, not a requirement to run full qualification before every assignment. Queued shared integration and final CI run at their normal stages. Test doubles remain valid for the decisions they actually demonstrate.

Classify remaining work before declaring a blocker. Unimplemented behavior owned by the issue is work to finish. A missing capability owned elsewhere is a prerequisite. A future consumer outside the issue's accepted scope is not additional acceptance. Do not create a circular requirement by making a foundation wait for the downstream feature that consumes it. A broad issue spanning absent target types can supply a reviewed prerequisite, but remains open until all its own promised behavior exists.

Before scheduling shared verification, inspect the actual retained database migration tip, candidate schema, generated outputs and their writers. A migration number on the branch alone does not establish compatibility with the shared environment. Order or isolate the maintained checks without resetting another owner's database or treating queued execution as missing implementation.

Do not start dependent behavior whose producer or required verification capability is absent. Deliver the smallest useful authorized prerequisite on the selected issue's closure path. A narrow supporting component still needs its explicit acceptance and independent verification. It does not establish that the whole issue can now close. Preserve accepted scope instead of substituting an unused library, speculative adapter or deferred automated test. Routine sequencing within that scope needs no new approval ceremony.

Require the capability, not completion of every related issue. A qualified supporting PR may supply the needed sign-in step while its broader owning issue remains open. Reassess native blockers against that actual delivered increment, recording why a broad edge is now satisfied. Never claim the larger issue is complete. Keep dependency relationships acyclic and avoid blanket parent/epic blockers.

For each human-facing feature, publish or reuse one linked qualification issue under actual authority and the [closure policy](gates-and-recovery.md#separate-implementation-and-human-acceptance). [Testing](../../inframeld-testing/references/human-qualification.md) owns its template, deferred contents, engineering preparation and human results. Internal work identifies its supported journey or a scoped non-applicability reason.

Use the [assignment brief](assignment-protocol.md#use-one-short-assignment-brief). Clear ownership once. Request independent plan review for material architecture, authorization, public-contract, persistence, shared-harness changes or a newly proposed cross-issue boundary. A routine implementation within accepted patterns needs a proportionate scope check and later independent implementation review, not another extensive planning ceremony.

For a material plan, apply Review's binding [maintainability bar](../../inframeld-review/references/scoring-and-report.md#apply-the-maintainability-bar) to the complete proposed capability, including verification infrastructure. Reconsider scope or approach when the bar is unmet, even on the first repair. Explain the actual burden and smallest safe alternative. Implementation-only evidence is N/A at planning time. Other scores describe the inspected quality and confidence. A preferred rating adds no acceptance requirement.

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

Use two implementation lanes for the delivery trial, within actual runtime capacity and any lower human-selected limit. Expand later only when the lanes routinely finish, a ready independent capability exists and review/integration capacity can finish it. Native maxima of ten workers, two code reviewers, one DX reviewer and one writer remain ceilings. Preserve specialist capacity and the launch's model allocation. Temporary model unavailability calls for bounded backoff and reduced dispatch pressure.

Give each shared migration tip, schema, application assembly point, public contract, generated output set and lockfile one named writer. Isolated implementation can proceed while the shared step waits. One coordinator allocates the shared integration executor and serializes merges. A separate worktree alone does not make these boundaries independent.

Use stable identities such as `impl_a`, `impl_b`, `review_a` and `docs` for new agents. Show the current assignment as `Implement · #901 Member administration`, alongside identity and status in the selection view. Keep existing identities and update their visible assignment mapping. Native tools expose no agent rename operation. A chat title change does not rename a native identity. Follow the [handoff protocol](assignment-protocol.md#return-a-useful-handoff) for fresh review, reuse and compaction. Still-open agents count against capacity until actually released.

## Prioritize completion when the run is overloaded

When several branches wait on the same prerequisite, review queues grow, or harness work dominates feature progress, stop opening new implementation assignments at a safe checkpoint. This pauses dispatch, not the Goal or a running command. Preserve current work and let safe operations finish.

List active capabilities, reviewed checkpoints, real blockers and the next expected whole-issue closure. Finish the selected issue or its necessary prerequisite through review, required checks and merge. Independent workers may still perform already assigned private checks, documentation and review. Keep truly blocked work parked. Reconcile ownership and apply the selection rule above before resuming dispatch.

Prioritize a narrowly scoped shared maintenance PR when it genuinely unlocks several qualified branches. Do not bypass hooks, weaken cleanup or add another execution framework to avoid that blocker. Review any expansion of the maintenance scope under [Testing's harness boundary](../../inframeld-testing/references/isolation-and-evidence.md#keep-harness-repairs-bounded).

Name the next useful PR and what still prevents it. If correction attempts create further infrastructure work while the same acceptance case fails, reassess the whole repair rather than approve only its next small patch. The [#237 case](case-237-testing-repair.md) illustrates why separate worktrees and scoped review scores alone do not establish progress.

### Park blocked work and reuse its worker

Preserve a recoverable checkpoint in the existing worktree with the exact blocker, next action and unblock condition. Obtain a positive writer-stop acknowledgment and reconcile all held resources. In native mode, `retire` releases the unfinished assignment only after verified cleanup. Retirement is not feature completion. Never delete a branch or discard dirty work to make room.

Recheck existing unfinished issues and the blocked issue's prerequisites under the selection rule above. Give a released worker a fresh worktree and brief only for the resulting assignment. Resume parked work through `adopt` after checking intervening main and contracts. Retirement releases resources, not the obligation to finish or return. It does not authorize an unrelated new issue.

## Own coordination, not every command

The coordinator is the sole run-state writer and shared-resource allocator. Use [existing helpers](../../../../scripts/delivery/README.md) in native mode. `plan` and `status` inspect, `init` and `apply` record state, and assessment commands assess supplied observations. Use explicit `--summary` for ordinary `status` and `apply` results. Keep flagless or `--full` output for existing full-state consumers and exceptional local inspection. Retain the actual record and original evidence under their custody, without saving its full echo after every routine update. The helper does not infer the next action. Supply that judgment in the brief and selection view. Helpers grant no authority or merge permission, and expected revisions do not make competing coordinators safe.

Record ownership before dispatch. Shared outputs need one writer or an acknowledged handoff. `amend`, `revise`, `adopt` and `retire` keep their implemented validation and evidence-invalidation rules. Reconcile actual writers and resources before changing ownership. A recorded merge alone does not release an assignment.

Grant a complete maintained integration operation to one executor under the [resource policy](gates-and-recovery.md#shared-resources-are-observed-ownership). Workers choose routine edits and isolated checks inside their brief. Avoid relaying every subprocess or creating a new permission receipt for each private formatter or test.

Use short event messages for selection changes, meaningful milestones, observed merges, material blockers and decisions. Routine commands and unchanged polls need no narration. The [authority clause](assignment-protocol.md#use-one-short-assignment-brief) governs direct grants, later restrictions, the named publisher and automatic denials.

## Merge, reconcile and measure

Follow [gates and recovery](gates-and-recovery.md), including current evidence, failure classification, serial expected-head merges and the host boundary. After an observed merge, notify affected workers of actual main and changed contracts. Rebase only at safe checkpoints and refresh affected evidence. Do not merge several PRs against stale main.

Keep ordinary progress updates short: report a meaningful result, changed gate, next action or needed decision. Use the table below only when selecting or replanning issue work. A subprocess result, PR push, routine review update or unchanged status poll does not trigger it.

### Report once at an issue-selection checkpoint

Show one compact Markdown table when choosing the initial batch, assigning or resuming an issue, or reconsidering eligible work after a confirmed completion, supporting merge or changed blocker. This includes a selection decision to wait rather than dispatch. Combine related choices into one checkpoint update. A completion without a new selection decision needs only a short event message, then appears in the next selection table. Never repeat the table each turn or solely because time passed.

Precede it with one line naming the focused epic, next expected whole-issue closure, remaining acceptance and why the needed capabilities are available. Distinguish this from the next supporting PR. If no closure is currently achievable, name the prerequisite or decision preventing it. Include active issues, relevant parked work, immediate candidates and issues completed since the previous selection checkpoint. Include deferred human qualification when it explains a closure. Keep one row per issue, active work first, using the existing table rather than another report.

Use these columns and values:

| Column | Allowed content |
| --- | --- |
| Issue | An existing `#N` issue reference, linked where practical. A PR is evidence, not an issue row. |
| Epic | Verified parent epic `#N` and short name. Use `(No Epic)` if none exists or `(Unverified)` if the relationship has not been established. Do not guess from the title. |
| Deliverable | A short description of the issue's promised capability. |
| Status | Exactly one label from the status table below. These are chat labels, not new helper stages or GitHub fields. |
| Completion unblocks | Only verified downstream issue references such as `#905, #906`, optionally linked, or exactly `(No Issue)` when no downstream issue is identified. Put an untracked benefit in Selection reason, not in this cell. Never invent a dependency or list the epic merely because this issue belongs to it. |
| Blockers | `None`, or concrete issue references and unmet conditions, a required decision, environment failure or missing evidence. Mark an unverified condition explicitly. Normal review/CI queueing and waiting for assignment capacity are not blockers. |
| Next action / owner | The concrete next step and responsible actor. For an agent, show readable role/issue/capability and stable identity, for example `Implement · #901 Member administration · impl_a`. Keep the finishing owner visible when a specialist owns the next action. Use `Unassigned` when no owner exists and `None` only for completed work needing no follow-up. Include remaining acceptance and the useful support PR. |
| Selection reason | A brief reason for selecting, continuing, waiting or deferring. Explain work outside the focused epic here. |

Use `(No Issue)` for an untracked capability or when no verified downstream issue is known. It does not assert that completion has no benefit. If relevant dependency evidence is unknown, name that uncertainty in Blockers or Next action rather than presenting it as verified.

| Status | Meaning |
| --- | --- |
| Backlog | Authorized future candidate whose readiness has not yet been established. |
| Ready | Prerequisites are verified and work awaits assignment capacity. |
| In progress | Implementation or remaining issue acceptance is being worked on. A merged supporting PR alone does not make the issue Done. |
| In review | The current delivery boundary awaits independent review. |
| In validation | Required automated checks or the final merge gate are pending. |
| Blocked | A concrete unmet prerequisite, decision, failure or evidence gap prevents the next step. Use this single label for stalled work too, with its condition and unblock action. |
| Deferred | Deliberately scheduled for later, including published pre-v1 human qualification. Distinguish that choice from an implementation blocker. |
| Done | Full implementation acceptance, actual merge and issue closure are verified under the existing closure policy. Pure human qualification needs accepted human results before Done. |

Do not introduce aliases such as Stalled, Partial delivery or Checks running. Record partial delivery and the remaining acceptance in Next action. Deferred human acceptance stays visible on its own linked issue, while the implementation issue may be Done under the existing policy. Unknown evidence cannot justify Ready or Done.

For example, these fictional rows show a selection after a supporting read PR merges:

| Issue | Epic | Deliverable | Status | Completion unblocks | Blockers | Next action / owner | Selection reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #901 | #900 Access | Member administration | In progress | #905 | None | Read PR #950 merged. Finish add/remove acceptance / Implement · #901 Member administration · impl_a | Finish the focused issue |
| #904 | #900 Access | Own permission inspection | Ready | (No Issue) | None | Select after #901 closes / Coordinator | New feature waits for existing completion |
| #905 | #900 Access | Safe departure | Blocked | (No Issue) | #901: membership changes must be delivered | Resume after #901's required capability merges / Coordinator | Preserve its checkpoint |
| #911 | #900 Access | Human Access qualification | Deferred | (No Issue) | None | Prepare walkthrough and execute before v1 / Engineering, then human tester | Published human work stays tracked |

Derive this view from existing issue, PR, assignment and evidence observations. It does not create assignments, change dependencies, expand scope, reset retries or modify either delivery mode's capacity or merge authority. The [Kanban Guide](https://kanbanguides.org/the-kanban-guide#defining-and-visualizing-the-workflow) supports explicit workflow states chosen for their context. This table is a small reporting view, not an additional project-management system.

At the agreed trial checkpoint, use existing records for one short outcome comparison. Distinguish complete issues, supporting merges and foundations used by a named consumer. Compare assignment-to-closure and support-to-consumer return, avoidable approval waiting, broad checks repeated on changed/unchanged inputs, repair convergence, material review rework and escaped failures. Separate elapsed time, recorded Goal time and observed waiting. Mark work already underway and unavailable data. Test, receipt and agent counts cannot measure delivery. No additional reporting ledger is needed.

Apply the [repair allowance](gates-and-recovery.md#classify-failures-and-bound-remediation) and continue independent authorized work where safe. Complete the Goal only when the finite authorized outcome is delivered and reconciled. Time, usage or a helper's `ready` result cannot establish completion.
