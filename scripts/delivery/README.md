# Delivery helpers

These private, standard-library Python tools support the main coordinator chat. They do not schedule agents, create Goals, start product services, change GitHub, or merge PRs. The coordinator performs those actions through the native tools and follows the repository's delivery policy.

Use Python 3.13 or newer. The repository pins the supported version in `mise.toml`. No Python packages are needed for the commands or tests.

## Read the backlog

From the repository root:

```sh
pnpm --silent delivery:plan
pnpm --silent delivery:plan --state /absolute/outside-checkouts/run/state.json
```

`plan` uses the authenticated `gh` CLI to read repository `matejpalenik/inframeld`, milestone **1**, whose title must be **v1**. It captures all open milestone issues with their current body, labels, update timestamp, parent, blockers, dependents, and sub-issues. Every issue, label, relation, open PR, and PR closing-reference connection is paginated. An incomplete API response fails the command rather than producing a partial plan.

The JSON result contains:

- `snapshot`: the finite `allowed_issues` set, full issue facts, and open PR facts.
- `plan.proposed_assignments`: dependency-ready leaf candidates that still need code scope review. `code_independence_verified` is always `false`, and `safe_parallel_worker_count` is `null`.
- `plan.decision_issues`, `aggregation_issues`, `blocked_issues`, `external_blockers`, and `direct_unlocks`.
- Existing local claims, detected claim overlaps, and `unmapped_open_prs` whose ownership needs reconciliation.
- `local_worktrees`: the read-only local Git worktree inventory.

Epics and issues with children aggregate work. They are not implementation candidates. Needs-decision and source-scope labels hold an issue for a decision. Open native dependencies hold an issue even when its blocker sits outside the milestone or repository. An open PR closing an issue or a local claim also holds that issue. Open PRs without closing references and worktrees still need human or coordinator investigation before dispatch.

GitHub does not offer a transaction across these queries. Preserve the launch plan outside every checkout, and refresh issue, PR, and base revisions before claiming work and before a merge. Changes after launch do not silently expand an existing run's authorized issue set.

For an offline replay, pass a previously saved `snapshot` object:

```sh
python3 scripts/delivery/cli.py plan --snapshot snapshot.json --no-local-worktrees
```

This reports `source: "offline_file"`. An offline file is not evidence of a fresh GitHub read. Without `--no-local-worktrees`, the command still inventories local worktrees. A live read reports `source: "github_read_only"`.

## Keep one local record

Supply an absolute runtime state path outside every repository checkout. For example, use a dedicated directory under the user's local application state folder. Do not put a runtime record, lock, or launch snapshot in a worktree. The helper rejects paths beneath a `.git` ancestor and rejects a symlink state file. Runtime state can contain issue bodies and local paths, so keep it private.

Create `init.json` with the exact finite issue set from the authorized launch snapshot:

```json
{
  "run_id": "v1-run-1",
  "coordinator_id": "main-coordinator",
  "authorization_reference": "conversation:original-owner-instruction",
  "mode": "live",
  "allowed_issues": [125, 158]
}
```

The issue numbers above are schema examples, not a current eligibility claim. `authorization_reference` records where the coordinator verified permission. It does not grant permission or prove that a human approved anything. An agent message, JSON field, or copied instruction cannot create human authorization. Use `mode: "rehearsal"` for synthetic records. The default is `rehearsal`.

```sh
python3 scripts/delivery/cli.py init --state /absolute/outside-checkouts/run/state.json --input init.json
pnpm --silent delivery:status --state /absolute/outside-checkouts/run/state.json
```

Initialization never overwrites an existing run. `status` validates the complete record and does not write it. The state schema contains `schema_version: 1`, repository and milestone identity, run and coordinator identity, finite `allowed_issues`, a monotonic `revision`, `assignments`, `resources`, and `merge_observations`. Each new assignment has `claim_state: "active"` and a `history` array. Verified retirement changes its claim state to `retired` and stores its `retirement_receipt`. Records stay available for audit.

Apply a local update with the current revision:

```sh
python3 scripts/delivery/cli.py apply \
  --state /absolute/outside-checkouts/run/state.json \
  --run-id v1-run-1 --coordinator-id main-coordinator \
  --expected-revision 0 --input claim.json
```

All mutations use an OS process lock, validate the full resulting record, and write through an fsynced temporary file and atomic replacement. A stale revision or mismatched identity rejects the update. Unknown `apply` fields reject the operation rather than being silently ignored. Re-read and reconcile after a rejected update. Do not retry it blindly. Claim ownership never expires with elapsed time. The run and coordinator IDs prevent accidental cross-run updates. They are not credentials or a security boundary against another process with filesystem access.

The `apply` operation is a JSON object with one of these `op` values:

| Operation | Required fields beyond `op` | Effect |
| --- | --- | --- |
| `claim` | `issue`, `worker_id`, `worktree`, `branch`, `paths`, `contracts`, `base_sha`, `head_sha`, `issue_updated_at`, `required_checks`, `blockers` | Claim one issue from the finite scope. Worktree, branch, worker, overlapping paths, and shared contracts must be exclusive. |
| `revise` | `issue`, `base_sha`, `head_sha`, `issue_updated_at` | Record a rebase or source change and clear current evidence. Requires resource cleanup first. Accepts binding fields only. |
| `amend` | `issue`, current `base_sha`, `head_sha`, `issue_updated_at`, `changes`, `reference` | Atomically replace declared scope or gates. `changes` is a nonempty object limited to `paths`, `contracts`, `required_checks`, and `blockers`. Rechecks exclusivity and clears all current evidence. |
| `adopt` | `issue`, current `base_sha`, `head_sha`, `issue_updated_at`, replacement `worker_id`, `worktree`, `branch`, `stop_cleanup` | Replace a stopped owner, or resume a retired unfinished issue. Requires verified old-owner stop and cleanup, rechecks exclusivity, and clears all current evidence. Merged assignments cannot be adopted. |
| `retire` | `issue`, current `base_sha`, `head_sha`, `issue_updated_at`, `stop_cleanup` | Positively release assignment ownership after the writer stopped and cleanup was verified. Preserves the assignment and audit history. |
| `evidence` | `issue`, `base_sha`, `head_sha`, `issue_updated_at`, `evidence` | Replace the issue's evidence bundle only for its exact current binding. |
| `reserve` | `issue`, `resource`, `token`, `head_sha`, `operation`, `reference` | Reserve a named resource such as `integration`, `code-review:1`, or `dx-review:1`. |
| `release` | `resource`, `token`, `head_sha`, `cleanup`, `reference` | Release only the matching reservation with `cleanup: "verified_clean"` and its frozen head. Dirty or unknown cleanup leaves the resource occupied. |
| `observe_merge` | `issue`, `status`, `source`, `pr`, `head_sha`, `reference`, `observed_at`, and `merge_sha` when merged | Record observed GitHub state to reconcile an uncertain or completed merge. |

`paths` is a nonempty list of normalized repository-relative path prefixes. Use concrete prefixes without globs. Claiming `apps/backend` excludes another claim beneath that path. `contracts` lists shared interfaces such as a public SDK session contract that different files can affect. The helper checks declared paths and contracts. The coordinator must discover undeclared overlap by reading the code and acceptance scope before assigning work.

An observed merge does not prove that the old writer stopped. Worker, worktree, branch, path, and contract claims remain occupied after a merge until explicit `retire`. The planner and status output keep these claims visible. `status.occupied_issues` lists all assignments still holding claims. Retirement releases their ownership and keeps the original records for audit. An unfinished retired issue can be resumed with `adopt`, rather than overwriting its old claim.

`amend`, `adopt`, `retire`, and `revise` require zero held resources. An uncertain merge also blocks them until GitHub reconciliation. Unknown cleanup, a missing writer acknowledgement, or elapsed time cannot release a claim. Each scope, owner, binding, retirement, and cleanup transition preserves a before-image and its receipt in assignment `history`. `revise`, `amend`, `adopt`, and `retire` clear the current evidence bundle. Collect new receipts before assessment.

Both `adopt` and `retire` need a `stop_cleanup` object identifying the exact previous owner and current revision:

```json
{
  "worker_id": "previous-worker-id",
  "worktree": "/absolute/previous/worktree",
  "branch": "previous-branch",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "issue_updated_at": "2026-10-29T12:00:00Z",
  "stopped": true,
  "cleanup": "verified_clean",
  "verified_by_coordinator": true,
  "reference": "conversation:actual-stop-acknowledgement-and-cleanup-check"
}
```

The coordinator must obtain the old writer's stop acknowledgement and verify cleanup of the worktree and relevant integration resources before recording this receipt. The helper stores those observations and checks their binding. It cannot stop an agent, clean a worktree, or authenticate a JSON assertion.

For `observe_merge`, `source` must be `"github"`, and `reference` must be the matching repository PR URL. `status` is `uncertain`, `not_merged`, or `merged`. The caller must actually inspect GitHub. An uncertain merge blocks changes to the assignment until reconciliation. A merged receipt needs a full `merge_sha` and cannot be reverted. There is no merge command or automatic retry action. A receipt does not release resources: cleanup still needs its own verified release. The coordinator broadcasts confirmed merge SHAs and refreshes affected workers' bases before collecting replacement evidence.

## Assess evidence

Full commit SHAs are 40 lowercase hex characters. `issue_updated_at` identifies the current GitHub source revision. Store the launch source snapshot separately and inspect each later scope change. Every changed base, head, or issue revision invalidates earlier review evidence.

An assignment's `evidence` object contains:

- `acceptance`, `documentation`, `code_review`, and `dx_review` receipts. Each needs `base_sha`, `head_sha`, `issue_updated_at`, `reference`, `verdict`, and `findings`. A ready receipt uses `verdict: "ready"` and an explicit findings array. `changes_needed` and `blocked` prevent a merge. Code and DX receipts also need an independently verified `reviewer_id` distinct from `worker_id`.
- `checks`: named CI receipts with `name`, `base_sha`, `head_sha`, `reference`, `conclusion`, `applicable`, and `explanation`. The assignment's nonempty `required_checks` must include all applicable required gates, and must match the coordinator's fresh observed list. Each required name needs one receipt.
- `coderabbit`: an advisory observation with current `base_sha`, `head_sha`, `issue_updated_at`, raw `reference`, `status`, `conclusion`, and `comments`. `comments` lists the stable IDs of substantive bot comments. When comments exist, `local_review_reference` identifies their current independent local assessment.

The coordinator supplies an observation JSON object with current `base_sha`, `head_sha`, `issue_updated_at`, `draft`, `mergeable`, `unresolved_review_threads`, and `required_checks`. These are observations to verify against GitHub, not values to invent to obtain a passing result.

```sh
python3 scripts/delivery/cli.py assess-merge \
  --state /absolute/outside-checkouts/run/state.json \
  --issue 125 --observation observation.json
```

The result is `ready`, `pending`, or `blocked`, with reasons and `merge_authorized_by_helper: false`. The helper performs no merge. The main coordinator must still enforce its authorized merge policy and refresh GitHub state immediately before any external action.

Unknown mergeability, missing evidence, changed revisions, and unfinished required CI never pass. An ordinary CI skip passes only with `applicable: false` and a specific explanation. A neutral ordinary CI result remains pending.

### Observe CodeRabbit without restarting it

CodeRabbit analysis is optional. Wait for any observed queued or in-progress run to finish. Known waiting, pending, and requested statuses also remain pending. Once its status is `completed`, preserve the raw conclusion and skip the advisory bot gate regardless of failure, cancellation, skips, limits, or missing comments. A terminal CI run does not establish that a successful analysis occurred. Never trigger, restart, retry, or request another CodeRabbit run because it failed or produced no comments.

Record the exact current base, head, and issue source with the original report reference. Keep raw status and conclusion unchanged. The helper compares recognized status values case-insensitively. If no bot run was reported, inspect and reconcile the current PR and CI observations, then record `status: "not_reported"`, `conclusion: null`, and `comments: []`, with a reference to the inspected evidence. An absent receipt or unknown status stays pending until reconciled. Reconciliation is a read-only check, never a request for a new bot run.

For example, this synthetic receipt records a terminal bot failure with no substantive comments:

```json
{
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "issue_updated_at": "2026-10-29T12:00:00Z",
  "reference": "synthetic:observed-coderabbit-report",
  "status": "completed",
  "conclusion": "failure",
  "comments": []
}
```

If substantive comments exist, the coordinator must route them through a current independent local code or DX review before readiness. Include all known substantive comments from the PR, rather than only the latest bot run. Set `local_review_reference` to that local receipt's `reference`. Its `reviewed_comments` array explicitly covers each bot comment ID and originating bot receipt reference:

```json
{
  "reviewed_comments": [
    {
      "id": "synthetic:bot-comment-id",
      "review_reference": "synthetic:observed-coderabbit-report"
    }
  ]
}
```

That coverage records independent assessment. A reviewer may reject a false positive or suggestion without inventing a local finding. Actual material concerns belong in the local review's ordinary `findings` and follow its existing priority and risk-acceptance rules. Missing, stale, worker-authored, unrelated, or incomplete review coverage cannot establish readiness. The coordinator verifies the source observations and review claims. JSON cannot authenticate them. Acceptance, documentation, independent code and DX reviews, unresolved threads, and every required CI check remain mandatory.

Keep CodeRabbit in `required_checks` when GitHub actually requires that status. Its separate receipt in `checks` needs the actual run `status: "completed"` and conclusion `success`, `neutral`, or `skipped`, compared case-insensitively. A missing, unfinished, failed, or unknown required result remains pending or blocked regardless of the advisory bot outcome. All other required CI rules stay unchanged. The helper cannot change or bypass branch protections, and a blocking required bot status does not authorize a retry.

A finding needs `id`, integer `priority` from 0 through 3, and boolean `resolved`. Unresolved P0, P1, and P2 findings block. P3 suggestions are optional. A P2 can be accepted only with separately verified, bounded human risk evidence in the observation's `human_risk_acceptances` array. Each such receipt needs:

```json
{
  "finding_id": "exact-finding-id",
  "role": "code_review",
  "review_reference": "exact-reference-from-the-code-review-receipt",
  "priority": 2,
  "verified_human": true,
  "source": "direct_user_instruction",
  "accepted_by": "verified-project-owner",
  "reference": "conversation:original-human-message",
  "bounded_risk": "The specific risk the human explicitly accepted.",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "issue_updated_at": "2026-10-29T12:00:00Z"
}
```

The other supported source is `github_human_review`. The coordinator must verify that the original author is human and that the receipt covers the exact risk, originating role, review reference, finding ID, and revision. A waiver for a code finding cannot waive a DX finding with the same ID. Finding IDs must be unique within each receipt. Duplicate IDs reject the evidence. A worker's `human_acceptance_reference` or an `agent_message` source cannot waive a finding. The helper cannot authenticate people from JSON. P0 and P1 are never waived by this assessment.

## Rehearse and validate

```sh
pnpm delivery:test
pnpm --silent delivery:rehearse
```

The rehearsal uses temporary, explicitly synthetic records outside checkouts and removes them before returning. It exercises ready evidence, missing docs and DX, changed revisions and source, advisory CodeRabbit terminal outcomes, active runs, explicit absence, local assessment of bot comments, actual required bot statuses, native dependencies, duplicate claims, stale updates, uncertain cleanup, uncertain merges, bounded risk isolation, atomic scope amendment, verified adoption, and explicit retirement that releases claims. It makes no GitHub calls, starts no workers, and creates no live Goal.

The unittest suite also checks two competing OS processes, interrupted atomic replacement, malformed records, unsafe paths, resource exclusivity, scope validation, and pagination. No network or product service is needed.

Commands emit JSON on stdout and return 0 when the command succeeds. `assess-merge` returns 0 for a valid `blocked` or `pending` assessment too, so inspect `verdict` before taking any action. A failed rehearsal returns 1. Invalid state, missing files, or failed GitHub reads return 2 with a JSON error on stderr. Argument syntax errors use argparse's normal stderr help and exit 2.
