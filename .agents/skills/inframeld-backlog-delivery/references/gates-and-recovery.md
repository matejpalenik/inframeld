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

## Shared resources are observed ownership

Workers request resources from the coordinator before starting shared integration activity. A claim names its owner, worktree/run and resource identity. Use one integration owner when the suite depends on shared Compose projects, fixed ports, database state or cleanup. Keep independent unit and fixture checks parallel when they do not use the same resources.

Release only after observing teardown and the actual resource state. A timeout, expired timestamp, killed terminal or missing agent response does not prove cleanup. Mark uncertain cleanup as still occupied, reconcile processes/containers/ports and then release. Do not broadly prune containers, delete databases, steal ports or terminate another agent's work. Resource state records coordination, not a substitute for actual sandbox permissions.

The run record lives outside every checkout, so rebases cannot overwrite it. The coordinator is its sole writer. Use run/coordinator identity and expected-revision updates, and inspect conflicts instead of overwriting newer records. Atomic state persistence prevents partial files. It does not make two independently acting coordinators safe.

## Merge the reviewed head serially

The helper's `assess-merge` reports whether supplied evidence is consistent and sufficient. It does not prove that uninspected GitHub evidence is authentic, authorize a merge or execute it. Before acting, the coordinator fetches current PR, issue, review, check and base state through supported tools and reconciles it with the record.

Require the branch to be frozen, the PR open and eligible, current base/head matching the checked revisions, accepted issue scope met, no unresolved material findings and all actual required gates satisfied. Recheck branch protections and use a supported expected-head merge guard. If the available merge tool cannot bind the operation to the checked head, do not perform an unguarded automatic merge. Obtain a supported path or escalate that capability gap.

Serialize merges so each subsequent PR is assessed against observed current main. Do not disable protections, bypass failed requirements, rewrite protected history or treat a local predicted merge as an observed GitHub merge. A merge call with an unknown outcome must be reconciled by reading actual PR/main state before retrying.

After a confirmed merge, record PR, merged head and actual new main revision. Notify affected workers and specialists of that revision, changed contracts and requested safe checkpoint rebase. Recompute unlocked issues and ownership. Do not claim work complete before the actual merge and necessary issue/status reconciliation.

## Reconcile after change or interruption

A push or rebase invalidates affected code/DX/docs/check receipts. A new main revision requires compatibility review even if the PR head is unchanged. Clear readiness until the worker updates and supplies appropriate new evidence. Avoid repeating irrelevant checks merely because time passed, but do not retain evidence whose premises changed.

On restart, compare recorded assignments with live agents, actual worktrees, branch heads, open PRs, check state and resources. Preserve dirty work and uncertain ownership. Adopt an existing compatible assignment only after confirming the previous owner cannot still write. Never create a replacement worker because a timestamp alone looks stale.

Stop the affected issue when three remediation cycles fail, a required decision is pending, a necessary external gate is unavailable or permission is missing. Continue independent work when possible. Report a concrete remaining action and its evidence. Do not mark a run or Goal complete because the state helper returns `ready`, because an issue was merely pushed or because available usage is low.
