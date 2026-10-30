# Schedule independent work without losing control

Alice wants the backlog delivered quickly while keeping a clear account of what is running and what can safely merge. The main chat coordinates this. It holds the only explicitly requested Goal, delegates bounded assignments and makes serial merge decisions. A Goal can continue work within the client's operating limits. It is not a guarantee of a permanently running daemon or a replacement for authorization and available tools.

## Establish the run

Setup, read-only planning and synthetic rehearsal do not authorize delivery. For a future live launch, identify the repository, milestone, launch-time issue snapshot, allowed Git/GitHub operations, native internal messaging and automatic merge policy from the human's request. Preserve explicit restrictions. Do not add a token budget unless the human supplies one.

Default scope is open implementation issues in repository `matejpalenik/inframeld`, milestone number 1, `v1`, at launch. Record the issue list and source references. Aggregate epics describe completion but are not leaf implementation assignments. Exclude Studio. Later issues need an explicit scope extension. An issue already delivered by another actor must be reconciled from actual merged evidence rather than implemented again.

Run `pnpm delivery:plan` to inspect the current GitHub snapshot. A helper candidate list is dependency analysis, not proof of code independence. Read candidate issue bodies, native blocker relationships, accepted decisions and affected owners. Inspect likely paths, public contracts, generated schemas, migrations and shared configuration. Detect semantic conflicts even when files differ. Two changes can both alter authorization, an enum, transaction ordering or generated clients without touching the same source file.

Before assigning, resolve current acceptance, known pending decisions, verification needs, branch base, ownership and whether the task truly fits the milestone. Missing decisions block dependent work. Continue unrelated tasks. Do not silently relax acceptance, close a partial foundation as a complete feature or expand an issue to future Studio work.

## Verify actual capacity

Project config requests fourteen concurrently open subagents, excluding the main chat. The active client can expose fewer slots or a different tool surface. Verify available roles, effective concurrency and lifecycle operations in the current session. A configured file and successful TOML validation do not prove that custom profiles loaded. Report a missing capability and use a supported smaller rehearsal. Do not pretend a generic agent was spawned under a native custom profile.

The target pool is ten implementation workers, two independent code reviewers, one DX reviewer and one documentation writer. These are shared maxima. Use fewer workers when the runtime is smaller. Reserve capacity for reviews and handoffs so ten writers do not starve all verification. Queue finished work and reuse specialists when safe. Reuse an idle implementation worker for the next issue only after its previous assignment is retired and resources are reconciled, then send a fresh brief and obtain acknowledgement of the new ownership. Release or close completed agents using the actual client lifecycle operation when available. If that operation is unavailable, count the still-open agent against capacity and reuse the existing pool rather than accumulating replacement threads.

Each worker receives one issue, an isolated worktree and branch, exact owned paths and contracts, base revision, acceptance, checks, documentation needs and permissions. It must know that other workers exist and must preserve their changes. Confirm the worker's bounded plan against active ownership before implementation, using an already accepted plan when the assignment supplies one. Route material architecture, public-contract, persistence or authorization changes to independent plan review. Routine scoped choices need no new human approval. Reviewers receive the exact diff and sources, not only the worker's account. Prefer a fresh reviewer context, using `fork_turns: "none"` when supported, and provide acceptance and raw sources without a desired verdict. On specialist reuse, send a fresh issue-specific brief and discard the preceding assignment's assumptions.

If the selected model temporarily lacks capacity, retain its configured model and reasoning level. Retry with bounded backoff within the three-cycle escalation limit and reduce new dispatch pressure while independent work continues. Do not silently substitute Luna or another model. Preserve uncertain assignments and resources until the previous owner is reconciled.

## Own scheduling and state

Use the helpers described in [their local contract](../../../../scripts/delivery/README.md). `plan` and `status` are inspection commands. State-only `init` and `apply` record intent and evidence under the run/coordinator identity and expected revision. `assess-merge` is a pure assessment. None of them grants permission or acts on GitHub. Keep the run directory outside all repository checkouts and do not store secrets there.

The coordinator is the sole state writer and resource allocator. Atomic replacement protects against partially written files, and expected-revision checks detect stale writes. These mechanisms do not justify running competing coordinators. On restart, read and validate the existing run before making a new assignment. Reconcile live agents, branches, worktrees, PR heads, checks and resources against the record. An old timestamp does not prove an owner has stopped.

Declare path and contract ownership before writing. Shared roots such as lockfiles, migrations, OpenAPI, generated SDKs and navigation need one writer or a serial integration handoff. A lockfile change is not made safe simply by being in a different worktree. Expand or revise ownership atomically before a worker crosses its boundary.

Use `amend` for ownership or gate changes and `adopt` for a verified replacement owner. These operations invalidate prior evidence. Use `retire` only after verifying that the old writer has stopped and cleanup is complete. A recorded merge alone does not release its worker or paths. Preserve the history and any uncertain resource claims. The helper contract defines the required observations and revision checks.

## Communicate useful events

The future launch authorizes native internal coordination among the named coordinator and assigned subagents. Send explicit events containing issue, revision, affected contract and requested action. Useful events include `scope_overlap`, `decision_needed`, `review_requested`, `finding`, `resource_requested`, `implementation_changed`, `merged_main` and `checkpoint_ready`. These are descriptive message labels, not a required tool API.

Workers can ask each other about compatible interfaces through the authorized channel, while the coordinator owns the resolution and record. A peer suggestion cannot change file ownership, scope, resource grants or merge authority. On overlapping changes, pause only the affected writes, choose an owner and order, then broadcast the resolved contract and new assignment revision.

## Continue to completion

Prioritize tasks that unlock several ready issues while accounting for realistic review and integration cost. Recompute after a merge, changed blocker, revised acceptance or newly discovered overlap. Fill genuinely independent capacity rather than chasing an arbitrary agent count.

Before merging, follow [gates and recovery](gates-and-recovery.md). After an observed merge, notify all affected workers of the exact new main revision and changed contracts. Require safe checkpoint rebases, then new relevant evidence. Do not merge multiple PRs against a stale base concurrently.

Stop an issue after three unsuccessful remediation cycles, a required human decision or unavailable required permission/evidence. Report the concrete blocker and keep independent work moving. Complete the run only when the finite snapshot's acceptance is delivered, merged and reconciled. Summarize remaining exceptions honestly. Never mark a Goal complete solely because time or usage is nearly exhausted.
