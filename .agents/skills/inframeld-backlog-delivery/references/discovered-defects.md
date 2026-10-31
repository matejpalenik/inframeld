# Decide what a discovered defect should interrupt

Alice is implementing a deletion-status endpoint when review finds unsafe cleanup in the SDK test runner. The endpoint lets her check her own deletion outcome. The runner starts test programs and stops them afterward. These are separate responsibilities, even when the runner is needed to verify the endpoint.

This reference owns discovery triage and its delivery disposition. [Documentation maintenance](../../../../docs/development/documentation-maintenance.md#author-delivery-issues) owns issue authoring. [Testing](../../inframeld-testing/references/isolation-and-evidence.md) owns commands and repair mechanics. [Gates and recovery](gates-and-recovery.md#classify-failures-and-bound-remediation) owns attempts, stops and risk acceptance. Read the [historical #237 case](case-237-testing-repair.md) when a tooling repair starts generating more repairs.

## Classify before expanding the assignment

The worker reports the observed problem and preserves the current feature checkpoint. The coordinator decides its disposition before assigning unrelated writes. Reuse the issue or assignment's existing record, with a short explanation of the symptom, evidence versus hypothesis, affected behavior or required check, owner, next action and unblock condition. Do not create another triage ledger.

| Discovery | Delivery disposition |
| --- | --- |
| The feature introduced a defect | Fix it in the feature, with its behavioral regression. |
| A pre-existing defect is unrelated to the feature's safety or required checks | Record it separately and prioritize it. Continue the feature through its ordinary gates. |
| A defect makes a required verification route unsafe or unable to establish acceptance | Deliver a focused prerequisite repair, use a reviewed existing equivalent route, or park the affected delivery. |
| An improvement is useful but unnecessary for accepted behavior | Defer it. It does not become a required review finding solely because it was noticed. |
| The environment needs prohibited host or VM repair | Stop affected runtime work under the host policy. Continue only verified independent work. |

An existing defect is not automatically a blocker and is not automatically safe to defer. State the concrete consequence for this delivery. Preserve Review's P0/P1/P2 rules and any required human risk acceptance. Logging an issue does not waive a finding.

## Prove the blocking relationship

Name the accepted behavior or actual required check, its invocation and the code path that encounters the defect. Explain why it cannot safely run or supply the promised evidence. Sharing a repository, language or authentication topic is insufficient.

For example, a CLI output change can be independent of backend behavior while its mandatory commit hook still executes an unsafe backend fixture. That is a verification dependency to inspect. Do not declare the change independent solely from its source paths. Conversely, do not make every SDK or platform check a prerequisite merely because one shared script changed. Inspect actual selection, hooks and protections.

Compare a small prerequisite PR with an already maintained alternative. An alternative must preserve required behavior, platform coverage, failure meaning and cleanup, and be reviewed before execution. Do not disable a hook, narrow a selector to hide a defect, skip a required check or substitute a private controller to create a green result. If no safe route exists, keep the feature blocked.

## Give the repair its own useful boundary

Choose one owner and a repair outcome that can be tested and reviewed independently. Another worker is useful only when ownership and resources permit it. The original worker can own the separate repair after preserving the feature checkpoint. A different issue or worktree alone does not make work independent.

The repair brief names the original defect, smallest safe correction, regression, affected maintained command, exclusions and next useful PR. Infrastructure repairs may change their owning runner or add a necessary narrow helper. Compare existing lifecycle mechanisms before introducing a supervisor, IPC protocol or cross-language execution layer. IPC means communication between processes. It is not a product requirement just because a test uses it.

Review the complete proposed repair against main, including supporting fixtures and new failure modes. A small last patch cannot establish that the accumulated solution is proportionate. Return to [recovery assessment](gates-and-recovery.md#classify-failures-and-bound-remediation) if the same acceptance case remains failing or the replacement needs substantial new corrections.

## Create a clear defect issue when authorized

The coordinator checks for an existing issue and is the publishing owner during a coordinated run. Workers may draft reports. A live launch can authorize creation and linking of incidental defect issues without another confirmation for each report. Read-only work, rehearsal, a skill and a peer message supply no such authority. When creation is not authorized, retain a draft and continue unaffected work.

Recording a defect does not add its implementation to a finite launch snapshot. A necessary supporting repair may remain under an existing authorized assignment while linking the separate defect. New assignments outside the allowlist need the launch's scope authorization. Preserve original blockers, failure history and issue acceptance. Never rename work to reset attempts or close the feature because the tooling repair merged.

Follow the existing [bug form](../../../../.github/ISSUE_TEMPLATE/bug_report.yml) and authoring guidance for the report's contents and language. The example below shows a source-supported risk without inventing a runtime incident or an accepted solution.

### Example: SDK cleanup can address the wrong process

**Problem and example.** Alice runs SDK verification. A test backend exits. The cleanup helper later sends a termination signal using its saved process-group number, which the operating system could have reused. Cleanup should remain tied to the original owned process. Review found the unsafe ordering. No actual termination of an unrelated process was observed.

**Evidence and impact.** Identify the inspected revision and source locations showing child reaping before the later signal. Add a regression that records signal ordering without forcing real identifier reuse. State which maintained SDK checks use the helper and why their execution is blocked.

**Proposed solution.** Compare the existing lifecycle API with retaining child ownership until the final signal and reaping afterward. Select the smallest mechanism that preserves safe cancellation, bounded cleanup, output and failure reporting. This is a proposal until reviewed and tested.

**Acceptance.** The regression detects the original unsafe ordering and passes after repair. Real owned-child tests cover relevant exit and cancellation behavior. The affected maintained workflow passes its required checks. Unknown cleanup stays a failure.

**Boundary.** Repair SDK test-process cleanup. Do not change deletion authorization, redesign general job execution, reconfigure the host or claim complete deletion-status delivery. Link the feature only if its required verification actually depends on this defect.

## Review decisions and learning

Keep the feature, tooling defect and supporting PR states distinct. A coherent commit or draft PR can precede final CI. Merge still needs its own accepted boundary, current required checks and independent review. [Supporting-PR policy](gates-and-recovery.md#merge-useful-prerequisites-without-closing-the-feature) owns that decision.

After a material delivery stall, capture the causal lesson and a small improvement with an owner and observable outcome. Add a realistic case to the existing [workflow evaluations](../../../../docs/development/guides/backlog-delivery.md#rehearse-and-evaluate-the-decisions). Do not turn every typo into a permanent rule or build a new metrics or evaluation platform.

The shape follows [Google's small-change guidance](https://google.github.io/eng-practices/review/developer/small-cls.html), [DORA's small-batch guidance](https://dora.dev/capabilities/working-in-small-batches/) and [Google SRE's actionable postmortems](https://sre.google/workbook/postmortem-culture/). The specific authorization and stop rules remain Inframeld policy.

Official OpenAI guidance on [bounded repair loops](https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex) and [evaluating skills](https://developers.openai.com/blog/eval-skills) supports checking actual progress and realistic decisions. It does not make structural validation proof of live delivery performance.
