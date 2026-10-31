# Case study: a deletion-status feature became a test-runner repair

Alice deletes the Support Project. Ordinary membership can disappear during deletion, but she still needs to ask whether her original operation finished. [Issue #237](https://github.com/matejpalenik/inframeld/issues/237) permits that content-free read only for its currently eligible initiating human. It does not restore the Project or expose its contents.

This is a historical case assembled on 2026-10-31 from inspected source and local delivery/review records. It describes the checkpoint before a completed tooling PR, rather than the issue's current status. Counts below are recorded evidence, not newly executed checks. The case teaches [discovery triage](discovered-defects.md). Domain policy remains with [operation recovery](../../inframeld-application-contracts/references/operation-recovery-contracts.md#deletion-status-inspection).

## What connected the feature to SDK testing

The implementation added an HTTP endpoint. OpenAPI describes the endpoint's URL, inputs and responses. Generated SDKs are client libraries that call it. The backend does not inspect SDKs. Repository delivery requires the HTTP contract and generated clients to agree.

SDK verification includes TypeScript in a real Chromium browser. Its runner starts a test backend and browser, executes checks and cleans them up. A test harness is this surrounding setup, controlled-failure and cleanup machinery. Process lifetime concerns when those programs start, remain owned and stop.

Before SDK execution, review found cleanup that could signal a saved process-group number after the original child had been reaped. Reaping collects a finished child and releases its identity. A later signal could address a reused identity. This was a source-supported safety defect, with no observed termination of an unrelated process. A similar backend-wrapper defect was also repaired. Parallel execution was not established as their cause.

## What the recorded repair stages established

These are meaningful changes grouped by purpose, not an exact count of every edit, command or TDD red. An intended failing regression is not automatically an unsuccessful remediation cycle.

| Stage | Recorded result and limit |
| --- | --- |
| Backend integration-wrapper repair | Twenty-five real integration cases and automatic cleanup passed through the repaired path. This did not qualify the SDK runner. |
| SDK retained-child ownership replacement | Review accepted the original signal-ownership correction at source level, but found paths that could mask a crashed process or lose captured output. |
| Crash and output-capture corrections | Those findings were resolved. Review then found that shutdown-time output overflow could escape the failure result. |
| Shutdown-output correction | Scoped process/backend review accepted the corrected behavior. Broader browser and platform qualification remained pending. |
| Separately surviving browser-owner fixture | Added recovery ownership when a test worker disappears, with IPC between fixture processes. Review found a hardcoded macOS temporary path unsuitable for Linux. |
| Portability correction | Focused checks passed. A report writer's inspection of a deliberately invalid path triggered the explicit one-shot stop. After further approval, a worker-loss probe passed, but the real positive timeout case failed. |
| Diagnostic extension | Added protected capture and phase records. The positive timeout case failed again. More information was available, but normal cleanup remained unqualified. |

The run's audit separately recorded three unsuccessful corrective handoffs before additional human-approved work. Several corrections worked within their stated scope. The later failures were not repeated demonstrations of the original signal-ownership defect.

At this checkpoint, the latest causal review reported a pending-promise/event-loop cancellation and a lost profile connection. It did not establish which internal cleanup await was pending or whether the cause was voluntary exit, lost liveness or a managed deadline. Emergency browser recovery eventually closed owned browsers, but could not count as successful normal profile cleanup. Do not teach an unproven socket-reference fix as the resolution.

## What worked and where the workflow lost focus

The useful practices were behavioral regressions, independent review, bounded execution, ownership-aware cleanup and honest failure reporting. The feature reader and real-credential HTTP tests progressed. Tests using seeded deletion history did not prove that a real deletion producer created that history.

The repair also introduced or exposed further defects in its replacement machinery. Reviews of individual corrections did not establish that the whole accumulated change remained the smallest maintainable solution. One source review rated its process/backend slice 8/10 for quality and 2/10 for overengineering risk while explicitly excluding browser qualification. That rating was not a verdict on the complete repair.

The work moved to a separate maintenance checkout, but still blocked delivery. A locally verified CLI increment also waited because its ordinary commit hook ran affected backend tests. Separate tickets and worktrees therefore did not remove actual verification dependencies. A proposed backend-only split still needed review of its complete changed paths and actual CI selection. It was not an established safe shortcut.

## The decision another delivery should make

When this pattern appears, preserve the feature checkpoint and record the tooling defect with one owner. Name the particular required checks it blocks. Compare a focused prerequisite PR, an existing supported equivalent verification path and parking the affected feature. Do not promise independent delivery merely because the product code is unrelated.

Before adding another correction, ask whether the original acceptance gap is shrinking and what the latest evidence rules out. If the same timeout case still fails, isolate the actual pending lifecycle operation at the smallest responsible boundary. A process/IPC defect may need a real owned-process test, while a deterministic decision can use a controlled collaborator. Neither requires inventing another general runner.

Reconsider the complete solution against main when replacement code needs substantial new fixes or supervision infrastructure. Preserve safety and required evidence while simplifying or splitting. Do not increase deadlines, accept emergency cleanup as normal success, waive a required finding or change host configuration merely to finish.

Follow the existing cumulative three-cycle and one-shot restrictions. Moving the repair to a new issue, worker, worktree or stage does not reset them. Another approval should choose a concrete repair or delivery boundary with a stopping point, rather than authorize an unchanged repetition.

The outcome to seek is a useful, independently reviewed tooling PR with its own passing checks, followed by feature delivery. Until that happens, additional tests, receipts or high scores for a narrow patch are activity, rather than proof that the full delivery is converging.

## Use the case to evaluate the skills

Give a fresh trial the failure evidence and current restrictions without the intended answer. It should distinguish feature behavior from verification tooling, map real blockers, preserve the checkpoint and select a bounded next action. Include a control where an unrelated tooling improvement should simply be deferred. [The evaluation guide](../../../../docs/development/guides/backlog-delivery.md#rehearse-and-evaluate-the-decisions) owns the reusable trials and their evidence limits.
