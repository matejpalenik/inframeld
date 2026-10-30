# Coordinate backlog delivery from one chat

The main chat is the coordinator. It can hold one explicitly requested Goal while native subagents implement and review bounded assignments in separate worktrees. Workers do not need their own Goals. The coordinator owns scheduling, shared resources, current acceptance and the decision to merge an eligible PR.

The checked-in setup prepares this workflow and a read-only rehearsal. It does not start a live backlog run. The local helpers inspect issues, maintain evidence and assess supplied merge observations. They do not spawn agents, create Goals, push branches, create PRs or merge them.

## Roles and capacity

| Role | Responsibility | Shared target maximum |
| --- | --- | --- |
| Main chat | Scope, Goal, scheduling, ownership, resource grants, merge decisions and rebase notifications | One coordinator |
| `inframeld_worker` | Plan and implement one issue, verify it, address findings and own its Git operations | Ten |
| `inframeld_code_reviewer` | Independently review a plan or exact base/head using the existing Review skill | Two |
| `inframeld_documentation_writer` | Write plain-language user pages and supported examples in allocated Protocol MDX paths | One |
| `inframeld_dx_reviewer` | Review supported CLI and SDK journeys, automation and recovery | One |

Profiles live in [`.codex/agents`](../../../.codex/agents/). Every profile explicitly selects GPT-6.1 Sol (`gpt-6.1-sol`) with Extra High (`xhigh`) reasoning. Project coordinator and fallback subagent defaults use the same settings. Preserve this model choice unless the human changes it. The project config requests fourteen concurrently open subagent slots. Actual availability can be lower. Verify the active client's effective limit and that it exposes the four actual role names. Parsing TOML alone does not establish that profiles loaded.

Open a fresh trusted session rooted in this repository after adding or changing profiles. Switching the editor's folder does not change an existing chat's working directory or reload its native role schema. Invoke each actual project type and distinguish advertised capacity from the concurrency demonstrated by successful spawns. If a client reports `unknown agent_type`, resolve its session root, trust or capability gap before live delivery. Do not substitute a generic agent and describe it as a verified custom profile.

These are shared specialist pools. Do not create four permanently allocated agents for every issue. Reserve enough capacity to finish reviews and documentation, reduce worker concurrency when review queues grow and count still-open agents until their lifecycle is actually released.

The main chat loads [Backlog Delivery](../../../.agents/skills/inframeld-backlog-delivery/SKILL.md). Workers load repository coding/language/domain guidance. Code reviewers use [Review](../../../.agents/skills/inframeld-review/SKILL.md). Writers use [Documentation](../../../.agents/skills/inframeld-documentation/SKILL.md). DX reviewers use [Developer Experience](../../../.agents/skills/inframeld-developer-experience/SKILL.md) and Review. All assigned roles follow the [assignment protocol](../../../.agents/skills/inframeld-backlog-delivery/references/assignment-protocol.md) before checks and handoffs. These project roles leave personal agents and the earlier global multi-chat delivery skill unchanged.

## Inspect the current backlog

Run these commands from the repository root:

```bash
pnpm delivery:plan
pnpm delivery:rehearse
pnpm delivery:test
```

`delivery:plan` reads repository `matejpalenik/inframeld`, milestone number 1, `v1`, through the authenticated GitHub CLI. It returns a snapshot, dependency candidates, blockers, ownership conflicts and likely unlocks. It makes no GitHub writes. A candidate is not proof that its code can change independently. The coordinator must inspect affected paths and semantic contracts before assignment.

`delivery:rehearse` uses temporary synthetic rehearsal state and demonstrates gate outcomes without GitHub calls. `delivery:test` runs the helper's behavioral unit tests. These commands do not exercise native role loading or prove that a full delivery run can launch.

The future scope is a finite snapshot of open implementation issues at launch. Exclude Studio and treat aggregate epics as completion summaries rather than leaf assignments. Later issues do not silently enter the run. An issue blocked on an accepted decision remains blocked while independent tasks can continue.

## Keep run state outside checkouts

Choose an authorized absolute run directory outside every repository checkout. A suitable local location is a dedicated directory under the task workspace's parent, provided it is writable in the active session. Do not put runtime records into a branch or broaden sandbox access to a global configuration directory merely to store them.

Inspect an existing record with:

```bash
pnpm delivery:status --state /absolute/outside-checkouts/run/state.json
```

The [helper contract](../../../scripts/delivery/README.md) owns exact JSON fields and command flags. `init` creates a record with run/coordinator identity, mode, authorization reference and finite allowed issues. `apply` requires those identities and the expected revision for state-only claim, revision, evidence, resource and merge-observation operations. `assess-merge` evaluates supplied evidence without merging. It returns exit status zero for a valid blocked or pending assessment too, so inspect the JSON `verdict` rather than treating command success as merge readiness.

Only the coordinator writes the run record and grants shared resources. Atomic persistence prevents partial records and revision checks reject stale writes. Neither mechanism authenticates a claim or makes competing coordinators safe. On restart, reconcile recorded agents, branches, PRs and resources against actual state before dispatching replacement work. Unknown cleanup remains occupied until observed otherwise.

## Rehearse before a live launch

In the main chat, a read-only request can be:

> Use `$inframeld-backlog-delivery` to rehearse the current v1 backlog. Inspect the issue snapshot, identify independent candidates and likely semantic conflicts, verify available native roles and capacity, and show proposed assignments and merge gates. Keep GitHub, product systems and repository files unchanged. Do not create a Goal or start live delivery.

The coordinator should return the inspected snapshot, proposed first wave, blockers, ownership boundaries, specialist queue and capability gaps. Where native custom profiles are unavailable, report that limit. Do not relabel generic agents as verified custom profiles. Synthetic gate tests remain useful, but are separate evidence.

## Launch only from an explicit live request

A future launch request must identify the scope and permitted actions. For example:

> Use `$inframeld-backlog-delivery` in this main chat to deliver the launch-time snapshot of open implementation issues in `matejpalenik/inframeld`, milestone 1 (`v1`), excluding Studio and aggregate epics. Create one coordinator Goal for that finite snapshot. Use the four project subagent roles within verified runtime capacity, with native internal messaging among assigned participants. Authorize issue worktrees, branch commits/pushes, PR creation/updates, required CI and CodeRabbit handling, and automatic merges only under the checked-head policy. After each observed merge, notify affected workers and coordinate safe rebases. Preserve sandbox restrictions, paid-call approval and the prohibition on production changes. Escalate material decisions or three unsuccessful remediation cycles while continuing independent work.

This example is a template for a later human instruction, not authorization from this document. Do not add a Goal token budget unless the human specifies one. A Goal supports autonomous continuation within current client limits. It does not guarantee indefinite unattended execution or authorize scheduled follow-ups.

## Deliver and merge the verified revision

Each issue has one worktree and one Git writer. The worker owns implementation and all Git operations. The documentation writer receives disjoint paths and hands edited files back to the worker. A named owner handles shared navigation. Shared lockfiles, migrations, OpenAPI, generated clients and integration resources require explicit ownership or serial handoffs.

The coordinator checks native dependencies and semantic overlap before dispatch. Workers report overlap before crossing scope. After implementation, independent reviewers inspect the actual base/head. User-facing documentation and DX applicability are explicit. Freeze all branch writes before final evidence. A changed issue, push, rebase or new main revision invalidates affected readiness.

P0 and P1 findings must be fixed. Required P2 findings block merge unless the human explicitly accepts that bounded risk and follow-up for the actual change. P3 suggestions are optional. Numerical scores explain quality and confidence, and are never a demand for endless polishing. Three unsuccessful remediation cycles escalate the remaining concern.

Required local checks, independent local reviews and final-head CI must be observed. CodeRabbit is advisory. Wait for its existing run to finish, route any substantive comments through independent local review, and skip analysis if it provides no comments for any reason. Never trigger or restart it manually. Record the actual bot result and review coverage without claiming that skipped analysis completed. Preserve GitHub settings and enforce actual required statuses under the [gate policy](../../../.agents/skills/inframeld-backlog-delivery/references/gates-and-recovery.md). The helper cannot authenticate review JSON, so the coordinator verifies original sources.

Only the coordinator merges, serially, using a supported guard for the checked head after rechecking current base, issue acceptance, actual branch rules and all required gates. It observes the result before recording completion. It then broadcasts the new main revision and changed contracts. Workers acknowledge a safe checkpoint before rebasing, resolve semantic conflicts, regenerate owned artifacts and obtain new affected evidence.

Complete the Goal only after the finite authorized snapshot is actually delivered and reconciled. A pushed branch, a helper's `ready` result or low remaining usage is not completion.

## Keep blocked issues from stopping independent delivery

When a new dependency appears, identify which accepted behavior needs it before expanding another feature's assignment. Independently review the smallest honest boundary: a documented prerequisite, an existing supported procedure, a useful supporting PR or an integrated delivery. Keep required findings open until properly resolved. See [dependency review](../../../.agents/skills/inframeld-backlog-delivery/references/coordinator.md#review-a-newly-discovered-dependency).

Preserve blocked work at a recoverable checkpoint, record its exact blocker and next action, obtain the writer's stop acknowledgment and verify resource cleanup. Retire the unfinished assignment before reusing that worker on a verified independent issue. Resume it later with `adopt`. The shared integration slot serializes integration execution, not unrelated implementation or private checks.

A supporting PR may merge a useful qualified capability while the larger issue stays open. Its scope, deferred dependencies and remaining acceptance need independent review. Use `assess-prerequisite` and `observe_prerequisite_merge`, retain all ordinary checks and merge guards, and use no closing references. Full-issue acceptance and completion counts remain unchanged. [Supporting-PR gates](../../../.agents/skills/inframeld-backlog-delivery/references/gates-and-recovery.md#merge-useful-prerequisites-without-closing-the-feature) own the details.

## Stop at the host boundary

Delivery may fix repository code, Dockerfiles and Compose/test configuration. It must not repair or reconfigure the host or Podman machine. The only machine-recovery exception is one coordinator-controlled start of an existing stopped machine, or one coordinated restart of a confirmed stuck machine, after reconciling other users. Failed or uncertain recovery stops runtime-dependent work. Changing VM networking/storage/settings, host trust/DNS/permissions, global tools, resetting/recreating machines and broad pruning are outside delivery authority. An extra issue-remediation cycle does not expand this boundary. See [host recovery and immediate stop conditions](../../../.agents/skills/inframeld-backlog-delivery/references/gates-and-recovery.md#keep-delivery-out-of-host-repair).

Future launch requests can add:

> Review newly discovered dependencies against accepted behavior before expanding an issue. Preserve blocked checkpoints and reuse stopped workers for verified independent tasks. Permit reviewed supporting PRs without declaring their larger issues complete. Use maintained acceptance commands and bounded diagnostic probes. Do not repair or reconfigure the host or Podman machine. Permit only the coordinated existing-machine start/restart exception in the delivery skill, then stop dependent work if recovery fails.

This example does not modify an existing Goal or expand an active run's authorization. Its coordinator must reconcile new guidance with the actual checked revision before adopting it.

## Rehearse the changed decisions

Use synthetic requests in isolated fresh contexts when permitted. Keep expected outcomes in the evaluator's private record rather than giving the answering agent an answer key. Include a newly discovered login prerequisite, a parked writer with an independent task available, a qualified supporting PR, an underqualified helper, a stopped machine, a hung machine shared with unrelated work, failed restart recovery and a proposed VM-network repair. Add ordinary explanation and standalone-review controls. Inspect loaded references and actual proposed actions. No real machine or live run mutation is needed to rehearse these decisions. Static walkthroughs and helper tests are not independent agent evaluations. Report unavailable evaluations explicitly.

## Configuration sources

The project uses current native standalone agent files and project-scoped configuration described in [OpenAI's subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). Role instructions do not create a separate security sandbox. Each agent inherits the parent session's permissions, and managed restrictions still apply.
