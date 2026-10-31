# Coordinate the separate-chat pilot

Alice wants two useful reviewed PRs ready for human merge. Use the repository's common scheduling policy while preserving this pilot's smaller pool and explicit chat permissions.

## Establish the pilot

Bind the assigned checkout through the personal entry point. Read `.agents/skills/inframeld-backlog-delivery/references/assignment-protocol.md`, then `references/coordinator.md` in that repository skill. Those files own assignment briefs, scope review, dependencies, parallelism, parked work and completion-first recovery. This adapter owns only separate-chat mechanics and the personal record below.

Verify the direct human authorization for the issue allowlist, participating chats and delivery actions. Permission to contact workers must also cover their replies. Reuse existing authorization rather than asking per command. Do not create a new user-owned chat unless requested. Discover actual tools for inspection, messaging and waiting. A file containing a drafted message does not prove dispatch.

Use one coordinator and at most two implementation workers. The human merges even when checks pass. Do not enable auto-merge, bypass protection or import native automatic merge authority. Native role names and the native fourteen-slot configuration are not prerequisites for this mode.

## Maintain the existing personal record

Use `/Users/matej/.codex/delivery-runs/inframeld/<batch-id>/state.json`, outside every checkout. Preserve a supplied batch ID or choose a descriptive one within the authorized task. Inspect existing records before dispatch. Reconcile another active coordinator or uncertain ownership before overlapping work. Confirm access to the named directory. If unavailable, request task-scoped access or a human handoff. Do not change global permissions or silently start an unrecorded run.

The coordinator is the sole writer. Keep schema version 1 and the existing fields:

| Fields | Meaning |
| --- | --- |
| `schema_version`, `mode`, `batch_id`, `repo` | `1`, `live` or `simulation`, the batch and `matejpalenik/inframeld` |
| `coordinator_chat_id`, `allowed_issues`, `merge_policy` | Actual coordinator, approved issue numbers and `human_only` |
| `authorization` | Trusted human instruction/reference, participants and allowed actions, without credentials |
| `assignments` | Worker, worktree, branch/base/head, brief, ownership, stage, blockers and next action |
| `evidence` | Scope, review, commands/results, tested revision/environment, PR and limits |
| `integration_owner` | `null` or issue, executor, worktree, frozen revision, operation and observed lifecycle |

Write a complete temporary sibling file and rename it atomically. This prevents partial files, not competing coordinators. Keep the existing stages: `planned`, `implementing`, `reviewing`, `waiting_for_integration`, `waiting_for_ci`, `ready_for_human_merge`, `needs_human`, `merged` and `cancelled`. A supporting merge belongs in its evidence while the feature remains unfinished. Do not write native helper state through this adapter or invent a schema migration.

## Execute and hand off

Record ownership before sending a short brief to an authorized idle worker. Workers make routine scoped choices. Use the common gates reference for one designated integration executor, frozen source, cleanup and retry limits. Use current repository Testing, Review, Definition of Done and PR-template guidance. Verify actual independent review capability. A profile name in prose does not prove invocation.

When work stalls, preserve its checkpoint and stop its writer positively before releasing ownership or reusing the chat on a fresh assignment. Use the common completion-first procedure when queues grow. No independent work verified means no new dispatch. A recurring host fault stops affected runtime work without consuming extra host-repair attempts.

For a supporting PR, assess the common gate criteria directly: independently reviewed useful scope and deferred dependencies, current base/head and acceptance, applicable code/documentation/DX review, resolved material findings, required checks and closing-reference inspection. Record that assessment with its original evidence in the existing `evidence` field. Do not call native assessment or merge-observation helpers. Hand the qualified PR to the human. After the human merges, record the PR, supported scope, merged head, actual new main, remaining acceptance/blockers and confirmation that the feature issue remains open. Keep the assignment unfinished until full acceptance is delivered. An uncertain merge keeps dependent execution and ownership changes blocked until reconciled.

After an actual human merge, observe current main, reconcile dependent work and request safe checkpoint updates. `ready_for_human_merge` is not `merged`. Unknown cleanup or merge state remains unresolved. Wait on meaningful changes rather than tight polling. Scheduled follow-ups require a separate request.

For rehearsal, use synthetic issues and proposed messages only. A future live launch must identify its real batch, chats and permitted actions. Goal creation is optional and requires an explicit human request. A pilot Goal's completion follows its requested outcome, such as reviewed PRs ready for human merge. Native backlog completion rules do not silently change that outcome.
