# Deliver one useful assigned capability

Alice owns a CLI output change while another worker implements independent backend behavior. She can write and test her change without waiting for every command to be acknowledged. Shared contracts and integration resources still have one coordinated owner.

## Accept the brief and clear overlap

Follow the [assignment protocol](assignment-protocol.md). Read repository and directory instructions, Coding Standards, affected language/package guidance and the owning behavior. Load required component references before affected code work. Use Application Contracts for execution/transport boundaries and SDK guidance for generated clients. Do not load every skill for a narrow change.

Confirm the useful outcome, acceptance examples, exclusions, base, owned paths/contracts, dependencies, permitted actions and verification commands. Return a short plan for the coordinator's ownership check, or use an already accepted plan. Material architecture, security, public-contract, persistence or shared-harness changes need independent plan review. Resolve pending human decisions before dependent implementation. Routine choices within the cleared brief need no repeated permission.

Apply Review's [maintainability bar](../../inframeld-review/references/scoring-and-report.md#apply-the-maintainability-bar). Before expanding into a new executor, supervisor, IPC protocol, store, dependency or alternative verification path outside the accepted approach, stop dependent expansion and report the failed behavior, evidence, smallest maintained alternative and maintenance cost. The coordinator chooses a simpler reviewed plan, a separately scoped repair or a parked checkpoint. Ordinary helpers and corrections within the accepted approach continue without a new approval ceremony. Preserve necessary safety and existing retry history.

Report overlap before crossing a path or contract boundary. Different worktrees do not authorize competing lockfile, migration, generator or common CLI changes. Ask for one owner or serial handoff instead of inventing an adapter to avoid alignment. A newly discovered dependency needs the coordinator's [accepted-behavior assessment](coordinator.md#review-a-newly-discovered-dependency), not automatic permission to absorb another feature.

For a discovered defect, preserve the feature checkpoint and report the observed example, evidence, affected check and proposed disposition under [defect triage](discovered-defects.md). Draft a clear issue when useful. During coordinated delivery the coordinator owns publication and assignment changes. Do not silently repair an unrelated component, publish duplicate reports or treat a new issue as a fresh retry allowance.

## Implement and test through the workspace

Follow scaffold-first behavioral TDD. Establish the necessary public seam, require the intended behavioral failure, implement the smallest real correction and refactor with focused tests green. Fix collection and setup errors before interpreting a red test. Do not add architecture-enforcement tests or speculative infrastructure.

Run scoped isolated unit and fixture checks using maintained commands. Existing examples include `pnpm --filter @inframeld/cli test` and `pnpm --filter @inframeld/backend test`. Their fast success does not establish service-dependent behavior. The [testing runbook](../../../../docs/development/guides/testing.md) owns focused flags, pinned configuration, disposable services and cleanup. Use its integration path, including `pnpm test:integration` where applicable. SDK qualification follows its runbook and required profiles. Do not invent a command for an unmerged account test interface.

Choose focused regression checks first, then applicable integration and final CI. Do not repeat the broadest suite after every edit. Preserve required coverage and actual branch checks. A small diagnostic can answer one unresolved question, but must return to a maintained acceptance path. [Testing](../../inframeld-testing/references/isolation-and-evidence.md#maintained-commands-and-diagnostic-probes) owns diagnostic limits and the [harness-repair boundary](../../inframeld-testing/references/isolation-and-evidence.md#keep-harness-repairs-bounded). A private execution controller is not a substitute for repository tests.

Request shared integration access with the worktree, frozen revision, maintained command and resources. The coordinator may designate you as executor. Once granted, run that operation and its documented cleanup without requesting permission for each internal step. Freeze the tested source until completion and cleanup are reconciled. Never infer a free stack from silence or elapsed time. Private worktree outputs need no shared-resource grant unless another task actually uses them.

Classify failures before changing unrelated code. Follow the [bounded remediation policy](gates-and-recovery.md#classify-failures-and-bound-remediation). Never repair the host or Podman machine. Request only the coordinator's permitted recovery under the [host boundary](gates-and-recovery.md#keep-delivery-out-of-host-repair).

## Keep documentation and review proportional

For user-visible changes, request documentation help with exact disjoint paths, the implementation revision and supported examples. An approved brief permits ordinary writing without repeated outline approval. The worker can maintain small documentation changes when no separate writer is needed. Public documentation and applicable DX evidence still need review. Internal-only work records a specific applicability reason.

You remain the sole Git writer. Inspect specialist handoffs and stop concurrent edits before staging owned changes. Do not capture or remove unrelated files with broad add/reset/clean operations. Commit coherent checkpoints through normal hooks under existing authorization. Pending final CI alone does not prohibit a useful commit or PR. Do not bypass an unsafe or required hook to force progress.

Request independent implementation review with the actual base/head, issue revision, delivered boundary, tests, raw evidence and known gaps. DX review applies to CLI/SDK setup, public output, automation, recovery and examples. Reviewers inspect the actual diff. Missing review is not a passing review.

Fix P0/P1 and required P2 findings, preserving the human's bounded P2 exception procedure. P3 suggestions remain optional. Re-review corrections and affected callers rather than restarting unrelated audits. Stop inventing work when no material finding remains. Scores never justify extra polishing.

Read the PR template. Describe concrete delivered behavior, useful limits and checks actually run. A supporting PR needs independently reviewed scope, useful acceptance and remaining feature work. Use no closing references unless the whole issue is delivered. Follow [supporting-PR gates](gates-and-recovery.md#merge-useful-prerequisites-without-closing-the-feature).

## Freeze, hand off and resume safely

Freeze all branch writes for final shared verification and review, including documentation and generation. Record actual base/head and current acceptance. New source, a rebase or changed acceptance requires current assessment of affected evidence. Revalidate unchanged earlier results explicitly rather than pretending they ran on a new revision. Required final-head CI remains required.

Under live authorization, push and prepare/update the PR. Observe the existing CodeRabbit run and route substantive comments through independent review. Never trigger or restart it manually. The [advisory policy](gates-and-recovery.md#evidence-for-readiness) retains mandatory local and GitHub gates. Return a current ready-for-assessment report. The worker never merges independently.

When blocked, preserve the branch and recoverable checkpoint, report the exact unblock condition and held resources, and stop writes before acknowledgment. The coordinator can safely release you for independent work. Do not transfer yourself or repurpose the old worktree.

After a relevant main merge, finish or safely stop active commands, freeze writers and acknowledge a checkpoint before rebasing. Resolve semantic as well as textual conflicts, regenerate owned artifacts through maintained commands and refresh affected checks/reviews. Preserve dirty work on interruption. Unknown cleanup stays occupied. Rehearsal ends with proposed actions, without implementation, services or GitHub mutation.
