---
name: inframeld-backlog-delivery
description: Coordinate an authorized Inframeld backlog through native workers, reviews and tested PRs, or rehearse that workflow read-only. Use for backlog orchestration and assigned delivery, not ordinary coding questions or standalone reviews.
---

# Deliver useful changes through a bounded backlog

Alice has a CLI output change ready for review while browser login waits for a prerequisite. The coordinator finishes the independent PR and schedules the shared integration stack for one executor at a time. A busy worker pool is not the outcome. Useful, reviewed capabilities reaching main are the outcome.

This skill owns Inframeld's common delivery policy and the native main-chat workflow. The personal `inframeld-delivery` adapter uses the common references with its explicit separate-chat mode. Loading either skill grants no implementation, messaging, Goal or GitHub authority. Preserve the actual launch's finite scope, sandbox, paid-call restrictions, production boundaries and merge policy.

## Select the role and reading route

Every assigned role reads the [assignment protocol](references/assignment-protocol.md) for checkout binding, authority and handoffs. Then load only the procedure needed:

| Task | Read |
| --- | --- |
| Select work, resolve dependencies, limit parallelism or adopt an overloaded run | [Coordination and scheduling](references/coordinator.md) |
| Discover an incidental defect or decide whether a repair should block delivery | [Defect triage](references/discovered-defects.md), with the [historical #237 case](references/case-237-testing-repair.md) for an expanding test-runner repair |
| Implement an assignment and test its behavior | [Worker delivery](references/worker.md) |
| Schedule integration, assess evidence, recover or merge | [Gates and recovery](references/gates-and-recovery.md) |
| Rehearse, launch, evaluate or install the personal adapter | [Delivery guide](../../../docs/development/guides/backlog-delivery.md) |

The native main chat holds the one explicitly requested Goal. Workers and specialists do not create their own Goals. Native roles are `inframeld_worker`, `inframeld_code_reviewer`, `inframeld_documentation_writer` and `inframeld_dx_reviewer`. Preserve the human-selected `gpt-6.1-sol` and `xhigh` settings. Verify actual role loading and effective runtime capacity rather than inferring them from TOML. The personal adapter retains its separate-chat permissions, two-worker ceiling and human-only merges. Do not mix operating modes.

## Keep the assignment small and the worker autonomous

Assign the smallest coherent useful capability with acceptance examples, exclusions, owned paths/contracts, real dependencies and maintained verification commands. It may complete an issue or form an explicitly reviewed supporting PR. Never claim partial work completes the larger feature.

The coordinator clears ownership once. Workers then make routine scoped edits, write behavioral tests and run isolated checks without per-command acknowledgments. Independently review plans for material architecture, security, public-contract, persistence or shared-harness changes. Every delivered implementation still receives independent review. Resolve triggered human decisions before dependent work.

Parallelize verified independent work. Serialize overlapping contracts, shared outputs and integration execution. Ten implementation workers, two code reviewers, one documentation writer and one DX reviewer are native ceilings, not occupancy targets. Use fewer when review, integration or dependencies limit completion. Finish current qualified work before opening more assignments when queues grow.

## Verify through maintained commands

Use repository-owned behavioral unit and integration tests and documented workspace entry points. A temporary diagnostic answers one bounded question and remains partial evidence. Do not replace acceptance with private controllers, repeat variants without new evidence or grow a harness repair into a general framework. [Testing](../inframeld-testing/references/isolation-and-evidence.md) owns those boundaries.

Classify discoveries before absorbing them. Publish clear incidental defect issues only under actual issue-creation authority. Logging a defect does not admit new implementation to the finite snapshot or waive a required check. Review the complete repair again when its scope grows or corrections stop converging.

The coordinator alone writes run state and allocates shared resources. It may designate one worker to execute a frozen revision's maintained integration operation. Observe exit and cleanup before releasing that resource. Private worktree outputs and isolated tests need no new resource grant unless they collide with another owner. Helpers record and assess observations. They do not authorize actions or authenticate evidence.

Delivery does not authorize host or Podman-machine repair. Only the coordinator may use the [single existing-machine start/restart exception](references/gates-and-recovery.md#keep-delivery-out-of-host-repair). Failed or unconfirmed recovery, recurrence or a need for deeper repair stops affected runtime work immediately.

## Finish and report honestly

Follow the [three-cycle and failure policy](references/gates-and-recovery.md#classify-failures-and-bound-remediation). Keep required findings and checks enforced. Preserve current base/head binding while reusing unchanged evidence only after explicit revalidation. CodeRabbit remains advisory under its existing policy. Review's [maintainability bar](../inframeld-review/references/scoring-and-report.md#apply-the-maintainability-bar) is binding for plan and implementation readiness. Other ratings remain descriptive, not arithmetic merge gates.

The coordinator performs authorized native merges serially with an expected-head guard and observes actual main afterward. Park blocked checkpoints and reuse safely released capacity for independent work. A Goal completes only when its authorized outcome is actually delivered and reconciled. Low usage, a pushed branch or a helper's readiness result does not establish completion.
