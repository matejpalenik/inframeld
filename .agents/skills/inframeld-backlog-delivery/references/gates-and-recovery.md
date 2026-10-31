# Bind evidence and merges to the actual change

Alice has a green PR, then rebases it after another issue merges. The earlier review and CI describe a different change. The coordinator must not combine those old results with the new head and call it ready. Evidence identifies exactly what was examined and which acceptance it satisfies.

## Evidence for readiness

Use the state and observation shapes in [the helper contract](../../../../scripts/delivery/README.md). Each role receipt records the actual head, base, current issue revision, source/reference, verdict and findings. Independent code and DX reviewers must have a reviewer identity distinct from the issue worker. Keep code review, documentation, DX, local verification, CI and CodeRabbit evidence distinct. Applicable user documentation must describe the delivered implementation. An internal-only or non-DX change needs an explicit scoped reason, not an empty checkbox.

Required checks come from actual repository policy, branch rules and issue acceptance. Record their check identities and conclusions for the final head. A passing check on an earlier commit does not satisfy a final-head requirement. Canceled, missing, queued, unknown and failed required checks remain blocking. A skipped check needs an explicit applicability explanation and must be allowed by the actual required-check policy.

CodeRabbit is advisory. Wait for the existing run to complete before deciding whether it supplied useful comments. Record its actual status, conclusion and source reference. If it provides no substantive comments, skip its analysis for any reason, including file-count limits, rate limits, failure, cancellation or an empty response. Do not trigger or restart it manually, re-push solely to force a review, buy credits or trim valid scope merely to fit the bot. Normal implementation pushes may cause automatic runs, which are observed for their actual head.

When substantive bot comments exist, send them to the independent local code or DX reviewer before accepting final local readiness. The reviewer records which comments were assessed and adopts genuine material concerns into its ordinary findings. It can reject a false positive without inventing a defect. Local findings and their resolution remain governed by Review. Use the [helper contract](../../../../scripts/delivery/README.md) for comment coverage and current review references.

Local reviews, actual required CI results and branch protections remain enforced. Preserve GitHub settings. A bot's completed failure can be skipped as advisory analysis, but an actually required failing status cannot be rewritten as a pass. Actual CodeRabbit check conclusions of success, neutral or skipped are acceptable after its observed run completes and comment handling is reconciled. Missing or still-running required checks remain pending. If no bot run was reported, explicitly reconcile and record its absence without requesting another run. Optional analysis does not justify fabricated check results or a claim that a review happened.

P0 stops delivery and P1 must be fixed. Required P2 work blocks merge unless the human explicitly accepts the bounded risk and follow-up. An accepted exception records the finding, scope, authorizing human reference and follow-up for this base/head and issue revision. Verify the original direct human instruction or actual GitHub human review before supplying a separate human risk acceptance in the assessment observation. A worker's assertion that a finding was accepted is insufficient. The helper cannot authenticate a JSON claim. A general request to merge when there are no major problems is not acceptance of a particular unresolved defect. P3 suggestions remain optional. Review scores describe quality and confidence, not an arithmetic merge gate.

Bind each accepted risk to its originating review role, exact review reference and finding ID as well as the revision. Reviewers can reuse short finding IDs, so one acceptance cannot waive another reviewer's concern. Finding IDs must be unique within a single review receipt.

Revalidate current issue acceptance before merge. A changed issue body, updated blocker or material acceptance change invalidates the affected readiness claim. A foundation can close its own scoped issue when acceptance is met. It cannot close a complete feature issue merely because another issue might later connect it to an executable journey.

### Revalidate evidence without repeating unrelated work

A normal result needs the command, tested revision/content, relevant environment, actual outcome, raw-log reference where useful and accepted behavior it establishes. Keep separate role judgments where the helper requires them. Do not add a manifest, fingerprint, per-command review or second state system merely to describe a routine formatter or unit test.

Current helper receipts must still bind to the current base/head and issue revision. When binding changes, create a current assessment after inspecting the delta. It may cite earlier raw test results for unchanged relevant content with an explicit applicability explanation. Do not relabel an earlier run as freshly executed. A documentation correction need not rerun unchanged database behavior, while an authorization change may require broad requalification. Required final-head CI cannot be replaced by earlier results.

A broken optional report writer does not erase retained valid evidence. Recover the report from the raw result without inventing data. If required source binding, test outcome or cleanup cannot be established, keep that claim unverified. Tests passing before failed cleanup do not make a complete integration run successful. Re-run only what remains unknown or whose premises changed.

## Merge useful prerequisites without closing the feature

A supporting PR may deliver a coherent, useful capability from an unfinished issue. It must belong to the authorized snapshot and have explicit acceptance examples, accurate limits and no speculative unused framework. Independently review the scope against the full issue, identifying remaining acceptance and explaining why each deferred native blocker is unnecessary for this particular capability. Preserve those blockers on the issue and full assignment. A missing prerequisite needed by the supporting capability still blocks its merge.

For example, a maintained transient login helper may be useful before saved credentials, refresh and logout exist. Its own supported journey, failures, cleanup and documentation must be qualified. Merely compiling a helper or promising a future consumer is insufficient. Existing required findings cannot be waived by moving them into the remaining-work list.

Bind acceptance, code, documentation and DX receipts explicitly to the supporting PR number, scope and actual base/head. All actual required checks, current authorization, independent reviews, P0/P1/P2 rules, CodeRabbit handling and expected-head merge guard still apply. Inspect PR and included commit closing references. Supporting PRs use no closing keywords and leave the larger issue open.

In native delivery, use `assess-prerequisite` with the independently reviewed packet described in [the helper contract](../../../../scripts/delivery/README.md#assess-a-supporting-pr). It assesses only the supporting boundary and never reports issue completion. Observe its actual merge with `observe_prerequisite_merge`. Do not use full-issue `observe_merge` or invent a ready full-issue acceptance receipt for that event. The personal separate-chat pilot applies the same scope, review and check criteria through its [human-merge handoff and personal evidence record](../../../../scripts/delivery/personal-skill/references/coordinator.md#execute-and-hand-off), without invoking native helpers or adopting their schema. In either mode, unknown merge outcomes block further execution and ownership changes until reconciled. Confirm the feature issue stayed open, retain remaining acceptance and refresh dependent work against actual main.

## Shared resources are observed ownership

The coordinator schedules shared integration and records its owner. It may designate the implementation worker as executor. A grant covers one complete maintained operation, its documented startup/cleanup and bounded scoped diagnostics, with the executor, worktree, clean frozen revision, command and affected resource identities. It does not need a new grant for every internal subprocess. It cannot override a stricter actual launch restriction. Reviewers request evidence and remain read-only.

Use one active integration operation when Compose projects, fixed ports, database state or cleanup are shared. Freeze the tested source, including documentation/generation writers, until exit and cleanup are reconciled. Afterward verify source still matches the frozen revision. Integration evidence never qualifies a different content state.

Independent unit/fixture checks and a worker's private outputs can run in parallel under the assignment's existing permission. They need another resource grant only when another task actually shares those outputs or services. Never treat an engine-wide resource as private merely because the worktree is separate.

Release only after observing teardown and the actual resource state. A timeout, expired timestamp, killed terminal or missing agent response does not prove cleanup. Mark uncertain cleanup as still occupied, reconcile processes/containers/ports and then release. Do not broadly prune containers, delete databases, steal ports or terminate another agent's work. Resource state records coordination, not a substitute for actual sandbox permissions.

The run record lives outside every checkout, so rebases cannot overwrite it. The coordinator is its sole writer. Use run/coordinator identity and expected-revision updates, and inspect conflicts instead of overwriting newer records. Atomic state persistence prevents partial files. It does not make two independently acting coordinators safe.

## Classify failures and bound remediation

Before another attempt, classify the failure as product behavior, maintained harness/configuration, diagnostic/evidence setup or unavailable environment. State the remaining accepted behavior, root-cause hypothesis, proposed scoped correction and meaningful verification. Keep this in the existing issue history. Do not build another retry controller.

Compare the remaining failure with the previous attempt. State what actually improved, what evidence rules out a hypothesis and which acceptance remains unmet. More passing pure tests or better diagnostics can be useful without resolving the failed real journey. The [discovery policy](discovered-defects.md) owns whether that defect should interrupt the feature.

When the same acceptance case remains failing or replacement code needs substantial new corrections, reassess the complete repair against main before expanding it. Choose a smaller evidence-based correction, a useful prerequisite boundary, a reviewed maintained alternative or a parked checkpoint. Review fixtures and supervision costs with the implementation. A narrow patch's good score cannot certify the accumulated solution. This reassessment stays within the remaining authorization and attempt limit. It grants no additional cycle.

A remediation cycle is a bounded attempt to resolve a blocker through a hypothesis, correction and relevant verification. Count unsuccessful cycles on the issue, including harness/setup attempts that leave the blocker unresolved. An expected behavioral TDD red, individual subprocess or optional formatting repair is not automatically a failed cycle. Three unsuccessful remediation cycles stop that issue for human direction. Carry the unresolved history across phase changes, renamed probes, supporting PRs and worker reassignment. A new label does not reset the allowance.

| Failure | Response within existing authorization |
| --- | --- |
| Intended behavioral red while authoring a test | Continue TDD. Fix import/collection/setup errors before interpreting behavior. |
| Product or maintained harness test fails | Make a bounded evidence-based correction within scope and verify it. Preserve the cycle history. |
| Invocation or diagnostic setup is wrong | Correct the demonstrated setup error within the same bounded work. Do not claim it proves a product defect or allow endless setup variants. |
| Optional report formatting fails after valid raw results | Recover the report and preserve valid results. Repeat only missing evidence. |
| Required outcome, source binding or cleanup is unknown | Keep it unverified. Stop affected shared execution and reconcile before reuse. |
| The same failure recurs without new evidence | Stop repeating the command or variants. Explain the blocker and use only a justified remaining remediation attempt. |
| A pending contract/authority decision or prohibited host repair is needed | Stop dependent actions immediately, regardless of cycles remaining. |
| Three unsuccessful cycles | Report attempts, exact blocker and a concrete next decision. Continue only independent authorized work. |

Future approvals should authorize a scoped repair/qualification operation with its retry and safety boundaries. Do not introduce a generic “any unexpected failure stops all work” condition for ordinary delivery. Existing explicit one-shot or stricter human stop conditions remain binding until changed by the human. An extra cycle does not expand scope, host authority or permission to waive findings.

Unknown resource ownership, possible effects outside the authorized fixture or uncontained security risk can stop execution before the cycle ceiling. A safe source-only correction may continue only where it does not depend on the uncertain resource. Escalations identify what remains unproven, what each attempt established, why another attempt has a better basis and its exact stopping point. Do not ask merely to repeat an unchanged attempt.

## Keep delivery out of host repair

Delivery implements repository capabilities. It is not a host-administration or container-runtime repair task. This boundary also applies when a Debug or Docker skill suggests broader investigation. A retry grant, a new probe or an extra remediation cycle does not authorize host changes.

Use maintained repository commands and the [Testing diagnostic/harness policy](../../inframeld-testing/references/isolation-and-evidence.md#maintained-commands-and-diagnostic-probes). Stop extended host/guest forensics once evidence establishes that deeper repair is needed. Record the environment blocker instead of pursuing a workaround outside delivery.

The coordinator may inspect machine/runtime status and make one bounded recovery attempt for the same incident: start the existing stopped or crashed machine, or stop/start an existing machine confirmed stuck. First reconcile active integration commands and machine users. Preserve unrelated containers, volumes and services. If unrelated use is unknown or restarting would disrupt work outside the authorization, stop runtime-dependent delivery and report that blocker. Workers and specialists request recovery from the coordinator and never restart the machine themselves.

After that attempt, perform a bounded health check and reconcile owned resources before another test. If recovery fails, cannot be confirmed or the same fault recurs, stop affected runtime work. Do not reset the recovery allowance by changing the incident name, stage, worker or test. Unknown cleanup stays occupied. Independent work that does not use the unavailable runtime may continue.

| Situation | Delivery response |
| --- | --- |
| A repository Compose file allocates the gateway address dynamically | Diagnose the source-controlled setting and repair it within the authorized issue scope and retry limit. |
| The existing machine is stopped or confirmed hung | The coordinator may make the single coordinated recovery attempt above. |
| The machine still fails after that attempt | Stop dependent operations and report the environment blocker. |
| A proposed fix changes VM networking, DNS, storage, CPU/memory, mounts, backend/provider, guest services or packages | Stop. Do not reconfigure the machine, SSH into it for repairs or pursue extended guest/host forensics. |
| A proposed fix changes host DNS, routes, firewall, trust stores, broad permissions or global tool versions/settings | Stop. Repository delivery does not authorize these host changes. |
| A proposed fix resets/recreates/deletes the machine, migrates its storage or broadly prunes resources | Stop. Preserve the machine and unrelated data. |

Locked dependencies inside an assigned worktree or disposable test image, repository Dockerfile/Compose changes and cleanup of positively owned fixtures remain ordinary scoped delivery operations. They do not permit host-wide installation, reconfiguration or cleanup. An explicitly requested infrastructure task is separate work with its own authorization.

The [remediation policy](#classify-failures-and-bound-remediation) remains in force, but prohibited host repair stops affected runtime work immediately, even before the first cycle is exhausted. Report the failed command/phase, bounded observations, recovery attempted, resource state and what the user must resolve. Do not supply a script that performs the prohibited repair as the next delivery action.

## Merge the reviewed head serially

The helper's `assess-merge` reports whether supplied evidence is consistent and sufficient. It does not prove that uninspected GitHub evidence is authentic, authorize a merge or execute it. Before acting, the coordinator fetches current PR, issue, review, check and base state through supported tools and reconciles it with the record.

Require the branch to be frozen, the PR open and eligible, current base/head matching the checked revisions, the accepted delivery boundary met, no unresolved material findings and all actual required gates satisfied. A completing PR needs full issue acceptance. A supporting PR needs the explicit scoped assessment above and leaves the feature open. Recheck branch protections and use a supported expected-head merge guard. If the available merge tool cannot bind the operation to the checked head, do not perform an unguarded automatic merge. Obtain a supported path or escalate that capability gap.

Serialize merges so each subsequent PR is assessed against observed current main. Do not disable protections, bypass failed requirements, rewrite protected history or treat a local predicted merge as an observed GitHub merge. A merge call with an unknown outcome must be reconciled by reading actual PR/main state before retrying.

After a confirmed merge, record PR, merged head and actual new main revision. Notify affected workers and specialists of that revision, changed contracts and requested safe checkpoint rebase. Recompute unlocked issues and ownership. Do not claim work complete before the actual merge and necessary issue/status reconciliation.

## Reconcile after change or interruption

A push or rebase invalidates affected code/DX/docs/check receipts. A new main revision requires compatibility review even if the PR head is unchanged. Clear readiness until the worker updates and supplies appropriate new evidence. Avoid repeating irrelevant checks merely because time passed, but do not retain evidence whose premises changed.

On restart, compare recorded assignments with live agents, actual worktrees, branch heads, open PRs, check state and resources. Preserve dirty work and uncertain ownership. Adopt an existing compatible assignment only after confirming the previous owner cannot still write. Never create a replacement worker because a timestamp alone looks stale.

Stop the affected issue when three remediation cycles fail, a required decision is pending, a necessary external gate is unavailable or permission is missing. Continue independent work when possible. Report a concrete remaining action and its evidence. Do not mark a run or Goal complete because the state helper returns `ready`, because an issue was merely pushed or because available usage is low.
