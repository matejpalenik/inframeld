---
name: inframeld-backlog-delivery
description: Coordinate an explicitly authorized Inframeld v1 backlog run from the main chat using native worker, code-review, documentation and DX subagents, or conduct its read-only planning and rehearsal. Use for backlog orchestration, not ordinary coding, standalone reviews or general product questions.
---

# Coordinate a finite backlog with native subagents

The main chat coordinates delivery and remains the user's conversation. It can hold one explicitly requested Goal while workers execute bounded assignments. Workers and specialists do not need separate Goals. Profiles provide role instructions, worktrees isolate branches and the coordinator controls dependencies, resource ownership and merge decisions.

This skill does not start a live run merely by being loaded. Setup and rehearsal are read-only with respect to GitHub and product systems. A future explicit launch must authorize its finite scope and delivery actions. Preserve the parent's sandbox, paid-call restrictions and production boundaries. Native internal agent messaging must be part of the authorized run. It does not authorize messages to people or unrelated chats.

## Select the mode and role

Every coordinator-assigned role follows the [assignment protocol](references/assignment-protocol.md) for checkout binding, trusted instructions, resource ownership and evidence handoffs. For the main-chat coordinator, read [coordination and scheduling](references/coordinator.md). For an assigned implementation worker, read [worker delivery](references/worker.md). For final evidence, shared resources, merge/rebase and recovery, read [gates and recovery](references/gates-and-recovery.md). The [launch guide](../../../docs/development/guides/backlog-delivery.md) explains concrete commands and the separate setup, rehearsal and live-launch phases.

Use the four project profiles: `inframeld_worker`, `inframeld_code_reviewer`, `inframeld_documentation_writer` and `inframeld_dx_reviewer`. There is no coordinator profile. Project defaults and every profile explicitly select `gpt-6.1-sol` with `xhigh` reasoning, following the human's choice. Preserve that selection unless the human changes it. Verify that the active client exposes these actual native roles before relying on them. A TOML parse or a role name inside a prompt does not prove native loading.

This skill owns the native project workflow. The older personal `inframeld-delivery` skill describes a separate-chat pilot. Do not combine its worker cap or merge restrictions with this run's accepted native-agent policy.

## Keep the run bounded and accountable

The default future scope is a launch-time snapshot of open implementation issues in `matejpalenik/inframeld`, milestone 1 (`v1`). Exclude Studio and aggregate epics from implementation assignments. Do not silently add later issues. Recheck current issue acceptance and dependency state before assignment and merge. A decision-blocked issue stops that issue, while independent work can continue.

Target a shared pool of up to ten workers, two code reviewers, one DX reviewer and one documentation writer. Fourteen configured subagent slots are a ceiling, not evidence of current availability. Use the lower effective runtime limit. Reduce active workers when specialist queues, shared resources or semantic overlap become the bottleneck. Each issue has one Git writer and one worktree. Specialists are shared, not four permanently reserved agents per issue.

The coordinator alone owns the external run record and resource grants. Use [the helper contract](../../../scripts/delivery/README.md) for atomic state updates and revision checks. Store runtime state outside every checkout. Helpers plan, validate and assess. They do not dispatch agents, create Goals, authorize actions or merge PRs.

## Deliver to the checked revision

Acceptance, code review, documentation, DX applicability, local checks, final CI and the CodeRabbit observation must identify the current issue revision and exact base/head. A push, rebase, changed issue acceptance or new main revision invalidates the affected evidence. CodeRabbit is advisory. Wait for its existing run to finish, review any substantive comments through the independent local reviewers, and skip it if it provides none for any reason. Never trigger or restart it manually. Keep mandatory local reviews and actual GitHub-required statuses enforced under the [gate policy](references/gates-and-recovery.md).

P0 and P1 findings must be resolved. Address P2 findings unless the human explicitly accepts the bounded risk and follow-up. P3 ideas remain optional. Stop after three unsuccessful remediation cycles and escalate the concrete remaining concern. Do not use a numerical score as a merge gate.

Only the coordinator merges under the future launch authorization, and only the checked head after revalidating the base and required gates. Observe the actual merge, broadcast the new main revision and coordinate safe checkpoint rebases. Unknown merge or cleanup outcomes remain unresolved. Complete the Goal only when the authorized snapshot is actually delivered with required evidence, not when a helper reports readiness or a budget runs low.
