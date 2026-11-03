# Finish independent work without expanding the project

Alice has several active branches, one shared integration stack and a limited review queue. The coordinator's job is to turn that work into useful merged capabilities. Opening more assignments helps only when they can progress independently and there is capacity to finish them.

## Establish the run

Setup, planning and rehearsal do not authorize delivery. For a native live launch, obtain the repository, finite issue snapshot, permitted Git/GitHub operations, internal messaging and merge policy from the actual human request. Preserve paid-call and production restrictions. Create only the explicitly requested coordinator Goal, with no invented token budget. Separate-chat mechanics remain in the personal adapter.

When a later trusted human instruction explicitly resolves or replaces an earlier approval request, post an ordinary coordinator chat update identifying both messages by link, message ID or clear quoted context and stating what is resolved or superseded. The chat transcript is this record. Append a correction if the status changes, without adding a ledger or run-state field. The referenced human instruction remains the authority, not the coordinator's summary. If the client cannot dismiss the old question, make its superseded status clear in that update. Silence, elapsed time, peer advice and a generic continuation do not automatically erase a specific stop condition. Preserve all restrictions the later instruction did not change. If a delayed answer arrives after the PR merged under valid subsequent authority, explain that no additional cycle starts. The late answer supplies no retroactive justification for an unauthorized action.

Default native scope is the launch-time open implementation snapshot in `matejpalenik/inframeld`, milestone 1 (`v1`). Exclude Studio and aggregate epics from worker assignments. Use epic relationships to guide selection within that finite scope. Later implementation issues need authorization. Reconcile already delivered work from actual merged evidence. A closed specification issue does not prove an implemented prerequisite exists.

A live run needs actual authority to create, update and link qualification issues for human-facing features in its finite scope. Reuse existing human authorization without asking again for each ticket. Without publication authority, retain a draft and report the gap before the required handoff. Qualification tracking does not add an implementation assignment to the allowlist. A missing implementation prerequisite outside that scope still needs the existing scope authorization.

Use `pnpm delivery:plan` for the GitHub snapshot and dependency candidates. Inspect issue acceptance, native blockers, open PRs, unpublished work and likely contracts before assignment. The helper cannot establish code independence. Missing decisions block dependent work, while unrelated authorized work may proceed.

### Prefer epic completion without serializing the backlog

Choose a primary epic from the developer's priorities, actual dependencies and the capabilities its completion unlocks. For example, finish feasible identity and administration issues before opening more consumers that need them. Keep exact epic IDs and the current selection in ordinary run updates, not a fixed global sequence. Epics remain aggregate outcomes, not worker assignments.

Prefer finishing active delivery boundaries and feasible remaining issue acceptance within that focus over starting another partial foundation. This is a preference for useful completion, not the smallest issue count or a requirement to finish an entire epic before touching another owner. Keep the [prerequisite check](#check-prerequisites-before-assignment) and useful supporting-PR gates.

Parallelize verified independent work within the focus. Use available capacity for an outside prerequisite or another ready epic when it can finish without delaying focused work through shared contracts, review or integration contention. A blocked focus is not a reason to leave safe independent capacity idle. Conversely, available workers are not a reason to build unused machinery or grow a queue that cannot finish.

After a supporting merge, reconsider the owning issue's remaining acceptance before selecting unrelated work. Name its next action or concrete blocker and return condition in the existing brief and issue history. A necessary split may deliver useful behavior now while the issue remains open for missing implementation. [Tracked human-testing deferral](gates-and-recovery.md#separate-implementation-and-human-acceptance) is a separate closure decision.

When related API changes form one coherent reviewable capability, consider grouping them to avoid repeated generated-client qualification and review. Do not hold an independently useful ready PR for speculative batching or enlarge its accepted scope merely to close an issue. Reassess the focus when dependencies change or its feasible work is blocked. No worker quota, scoring formula or additional state record is needed.

### Check prerequisites before assignment

Follow one concrete user operation before dispatching a writer. Identify the capabilities consumed by the promised behavior and its required checks, including any human journey. Record their owners and inspected delivery evidence in the existing [brief](assignment-protocol.md#use-one-short-assignment-brief):

| Prerequisite | Evidence needed before assignment |
| --- | --- |
| Behavior | The required producer/interface exists in the intended base with accepted semantics |
| Verification | The maintained verification route and its necessary real capabilities exist and can be executed under actual authorization |
| Human journey | The capabilities needed for the promised user experience are delivered, or that journey is explicitly outside an accepted component boundary |

Inspect relevant code/interfaces, merged PRs and scoped evidence. An approved design, an open implementation branch, a closed specification or a mocked response does not establish a delivered capability. This is a source/contract check, not a requirement to run full qualification before every assignment. Queued shared integration and final CI run at their normal stages. Test doubles remain valid for the decisions they actually demonstrate.

Do not start a feature whose promised behavior or required verification depends on an unfinished capability. Prioritize the smallest useful prerequisite within authorization, or park the feature and assign verified independent work. If a narrow component is genuinely useful without the missing capability, establish its explicit accepted boundary and independent verification before starting it. Do not quietly convert a promised usable journey into an unused library, speculative adapter or deferred test. Existing human scope decisions remain authoritative, and routine choices need no new approval ceremony.

Require the capability, not completion of every related issue. A qualified supporting PR may supply the needed sign-in step while its broader owning issue remains open. Reassess native blockers against that actual delivered increment, recording why a broad edge is now satisfied. Never claim the larger issue is complete. Keep dependency relationships acyclic and avoid blanket parent/epic blockers.

For each human-facing feature, create or reuse its one linked `type:qualification` issue using the [maintained template](../../../../.github/ISSUE_TEMPLATE/human_qualification.md). Plan its concrete observations and prerequisites now. Automated delivery may defer the manual procedure, its engineering dry run and human execution under the [closure policy](gates-and-recovery.md#separate-implementation-and-human-acceptance). Obtain the complete tested procedure before assigning it to a human, rather than before implementation closure. Apply [Testing's human-qualification guidance](../../inframeld-testing/references/human-qualification.md). Several PRs for the same feature share that ticket. Internal changes identify the journey they support or a scoped non-applicability reason. Do not create another status ledger or copy the template into every skill.

Use the [assignment brief](assignment-protocol.md#use-one-short-assignment-brief). Clear ownership once. Request independent plan review for material architecture, authorization, public-contract, persistence, shared-harness changes or a newly proposed cross-issue boundary. A routine implementation within accepted patterns needs a proportionate scope check and later independent implementation review, not another extensive planning ceremony.

For a material plan, seek roughly 9/10 on the relevant quality rubrics and apply Review's binding [maintainability bar](../../inframeld-review/references/scoring-and-report.md#apply-the-maintainability-bar). Review the complete proposed capability, including verification infrastructure. Reconsider scope or approach when the bar is unmet, even on the first repair attempt. Explain the actual gap and smallest remedy rather than requesting a preferred score. Implementation-only evidence is N/A at planning time. The quality targets do not justify polishing optional details indefinitely or averaging away maintenance findings.

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

Keep ordinary progress updates short: report a meaningful result, changed gate, next action or needed decision. Use the table below only when selecting or replanning issue work. A subprocess result, PR push, routine review update or unchanged status poll does not trigger it.

### Report once at an issue-selection checkpoint

Show one compact Markdown table when choosing the initial batch, assigning or resuming an issue, or reconsidering eligible work after a confirmed completion, supporting merge or changed blocker. This includes a selection decision to wait rather than dispatch. Combine related choices into one checkpoint update. A completion without a new selection decision needs only a short event message, then appears in the next selection table. Never repeat the table each turn or solely because time passed.

Precede it with one line naming the focused epic, next expected issue closure and selected next issue or reason for no assignment. Use verified issue references, or state that no next closure is established. Include all active issues, parked blockers still relevant to this run, the immediate candidates being considered and issues completed since the previous selection checkpoint. Include deferred human qualification when it explains an implementation closure. Keep one row per issue, active work first. Do not copy the entire backlog, retain an ever-growing completed list or add a reporting ledger.

Use these columns and values:

| Column | Allowed content |
| --- | --- |
| Issue | An existing `#N` issue reference, linked where practical. A PR is evidence, not an issue row. |
| Epic | Verified parent epic `#N` and short name. Use `(No Epic)` if none exists or `(Unverified)` if the relationship has not been established. Do not guess from the title. |
| Deliverable | A short description of the issue's promised capability. |
| Status | Exactly one label from the status table below. These are chat labels, not new helper stages or GitHub fields. |
| Completion unblocks | Only verified downstream issue references such as `#905, #906`, optionally linked, or exactly `(No Issue)` when no downstream issue is identified. Put an untracked benefit in Selection reason, not in this cell. Never invent a dependency or list the epic merely because this issue belongs to it. |
| Blockers | `None`, or concrete issue references and unmet conditions, a required decision, environment failure or missing evidence. Mark an unverified condition explicitly. Normal review/CI queueing and waiting for assignment capacity are not blockers. |
| Next action / owner | The concrete next step and actual responsible worker, reviewer, coordinator or human. Use `Unassigned` when no owner exists and `None` only for completed work needing no follow-up. Include the remaining acceptance and useful PR reference when a supporting increment has merged. |
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
| #901 | #900 Access | Member administration | In progress | #905 | None | Read PR #950 merged. Finish add/remove acceptance / Worker A | Finish the focused issue |
| #904 | #900 Access | Own permission inspection | Ready | (No Issue) | None | Assign at the next safe handoff / Coordinator | Independent focus work |
| #905 | #900 Access | Safe departure | Blocked | (No Issue) | #901: membership changes must be delivered | Resume after #901's required capability merges / Coordinator | Preserve its checkpoint |
| #911 | #900 Access | Human Access qualification | Deferred | (No Issue) | None | Prepare walkthrough and execute before v1 / Engineering, then human tester | Published human work stays tracked |

Derive this view from existing issue, PR, assignment and evidence observations. It does not create assignments, change dependencies, expand scope, reset retries or modify either delivery mode's capacity or merge authority. The [Kanban Guide](https://kanbanguides.org/the-kanban-guide#defining-and-visualizing-the-workflow) supports explicit workflow states chosen for their context. This table is a small reporting view, not an additional project-management system.

Use existing observations to notice time to useful PR/merge, review/integration waiting, repeated checks without new evidence, harness versus feature work and avoidable approval requests. Do not build a metrics service or treat test, agent or receipt counts as delivery goals.

Three unsuccessful remediation cycles stop the affected issue under the owning failure policy. Host risk can stop affected runtime work sooner. Continue independent authorized work where safe. Complete the Goal only when the finite authorized outcome is actually delivered and reconciled. Time, usage or a helper's `ready` result cannot establish completion.
