# Give a person a runnable acceptance procedure

Bob needs an operator to recover his permission to rename the Support Project. The backend can verify an identity proof, but Bob also needs a supported way to sign in and produce that proof. A passing backend test does not establish that he can complete the task. A person should be given the actual steps, commands and expected results, without needing to reconstruct authentication or database internals.

This reference owns human-test design, preparation and execution evidence. The [human-qualification issue template](../../../../.github/ISSUE_TEMPLATE/human_qualification.md) is the single reusable issue format. [Delivery coordination](../../inframeld-backlog-delivery/references/coordinator.md#check-prerequisites-before-assignment) owns scheduling and authorized publication. [Issue authoring](../../../../docs/development/documentation-maintenance.md#author-delivery-issues) owns GitHub relationships and labels. [Delivery gates](../../inframeld-backlog-delivery/references/gates-and-recovery.md#separate-implementation-and-human-acceptance) own merge and closure decisions.

## Identify the human-facing feature

A human-facing feature changes a supported product user, operator or API/SDK developer task. Browser and CLI flows, documented API/SDK workflows, installation and recovery procedures, and meaningful output or failure changes can qualify. The unit is the accepted feature, not every function, internal refactor, commit or PR. Several PRs may deliver one feature and share its qualification issue. An internal helper can link the journey it supports rather than acquire an artificial manual test. Repository process-only edits use their existing authoring/editorial evaluations rather than inventing a product qualification ticket.

Every human-facing feature in an active or new delivery has one linked qualification issue. Reuse an open issue for the same delivery rather than one per PR or retry. If a previous accepted delivery's issue is closed and a relevant new feature change needs qualification, create a focused follow-up preserving the prior results. Do not cite an older pass as acceptance of changed artifacts. This rule does not automatically reopen closed issues or authorize a bulk historical backfill. Automated tests remain responsible for meaningful product, contract and integration coverage.

## Defer human work during automated delivery

Automated backlog delivery prefers scheduling human testing before v1 release under [Delivery's closure policy](../../inframeld-backlog-delivery/references/gates-and-recovery.md#separate-implementation-and-human-acceptance). Manual walkthrough preparation and its engineering dry run may also remain pending. They are requirements for later human handoff, not implementation closure. An explicit request for earlier human acceptance still applies.

Before implementation closure, create or reuse the feature's published linked qualification issue. Its deferred record identifies:

- The feature and implementation PRs, available artifact references and automated evidence.
- The human outcomes and important alternatives still to observe, with pre-v1 testing timing.
- Missing manual setup, procedure, artifact selection or dry-run work, with responsible owners and concrete prerequisites.
- Its current preparation and execution limits, leaving unperformed readiness items unchecked and human cases Not run.

A deferred issue can describe these gaps without runnable commands. Replace template instructions with concrete known facts and named outstanding work, rather than guessed invocations or unexplained placeholders. Complete the procedure below before assigning it to a person. Reuse one issue across the feature's PRs and link shared setup instead of creating a manual test per component.

Track missing product implementation in its owning implementation issue. The human ticket may depend on that capability, but its creation does not complete it or replace required automated qualification. Delivery owns which issue may close and when the automated engineering Goal is complete. This reference owns later human readiness and results.

## Prepare the procedure before asking a human

Open the qualification issue during feature planning when publication is authorized. At that point it can explain missing prerequisites and engineering work without pretending the procedure is ready. Replace template instructions before publishing. Use a concrete statement such as "The supported proof-handoff command is unavailable until the acquisition capability in #160 is delivered" instead of an unexplained placeholder or guessed command. Native blockers remain authoritative for unresolved implementation dependencies.

Before handoff, select the actual artifacts and environment. Provide reproducible disposable test data, account roles and the source of every identifier or input. Explain how to reach the starting state, including safe reset between cases. A tester should not need private implementation knowledge, a database console or an administrative token shortcut. Keep credentials in the existing supported private channel. Do not add seed endpoints, setup controllers or another test framework merely to simplify the ticket.

Write one ordinary success path first. Put each action next to its observable expected result. Give literal commands, working directories, browser URLs and actual UI labels. Include applicable stdout/stderr, exit status and resulting state. Explain dynamic IDs and revisions rather than promising fixed bytes. A variable needs a clear value source and substitution instruction. Screenshots can clarify an unfamiliar screen, but must not expose secrets or replace executable steps.

Follow the [Documentation skill's task-guide pattern](../../inframeld-documentation/references/page-patterns.md#task-guide-solve-a-known-problem) for prose and supported examples. Link shared setup from its maintained guide and add the feature-specific values here. Keep one owner for the procedure so an issue and a runbook do not become conflicting copies.

The worker or an assigned engineer follows the entire procedure under the task's actual execution authority, using the selected disposable artifacts and maintained commands. Record what ran, artifacts, result and limitations. Correct omissions and wrong expected output before handoff. Unavailable execution remains unavailable, not an inferred successful dry run. Engineering preparation and dry-run success do not count as the separate human acceptance run.

## Check the important alternatives

Add the cancellation, rejection and recovery paths that change a person's next decision. Give each distinct workflow its own case and initial state. Avoid a large unexplained list such as "verify replay, fencing and scope." Explain what the tester does, what they should observe and what must remain unchanged.

Distinguish existing automated evidence from the observations assigned to the human. Keep required security and data-integrity checks enforced. Deferring a manual case retains it for later human execution, rather than replacing it with a test-suite link. Changes beyond Delivery's standing human-testing deferral follow the existing scope/decision process. A failed security check, unresolved cleanup or missing implementation is not deferrable merely by labelling it human testing.

Human acceptance checks the supported experience as well as the outcome. Ask whether account/installation choices are clear, instructions are sufficient, errors give a useful next step and cancellation leaves understandable state. It complements automated coverage rather than repeating every unit case manually or proving all possible behavior correct.

## Worked example: the #120/#298 boundary

In the [#120](https://github.com/matejpalenik/inframeld/issues/120) and [#298](https://github.com/matejpalenik/inframeld/issues/298) situation, the Project metadata repair consumer and the supported human proof-acquisition journey were different capabilities. The maintainer explicitly deferred the complete operator journey while retaining the backend's authorization, provider, persistence, replay and generated-client requirements. That historical decision preserves its own scope. The current standing human-testing deferral comes from Delivery's closure policy, not an inference that missing product capabilities are complete.

Assume a similar consumer is delivered but its proof producer is not. The qualification issue explains the dependency and remains with engineering. It does not tell a person to obtain a token by unspecified means or invent a login command. A meaningful main case has these observations:

| Person's task | Expected observation |
| --- | --- |
| Record the supplied Project ID and sign in as the prepared member through the supported flow | Correct account and installation are visible, with no secret exposed |
| Use the documented protected handoff and host-authorized repair procedure | Safe receipt identifies the intended repair, with no unrelated permission changes |
| Change the Project Name using a delivered client and read it again | New Name is visible and the permanent ID matches the recorded ID |
| Cancel or follow the documented original-operation recovery case | No unintended mutation, duplicate grant or inferred success |

These are acceptance observations, not runnable commands. Before handing the actual issue to a person, the engineer fills each row with the real invocation/UI sequence, prepared values and exact expected output. Use the current owning workflow and delivered interfaces, not a historical example's assumed availability. Saved-account management, full Studio and unrelated login features do not become prerequisites unless the promised case actually needs them.

## Record runs and retain limits

Keep the reusable procedure in the issue or its linked maintained walkthrough. Add a separate result comment for each run using the template's execution fields. Record the tester, date, artifacts, environment, case, actual result and safe evidence. An engineering or automated run identifies itself and cannot be presented as the human's acceptance. Not run, Blocked and Failed remain distinct from Passed. Unexecuted cases cannot be inferred from successful adjacent steps.

If a step fails, record the exact expected and actual behavior and link the owning defect. Stop dependent steps when continuing would invalidate the starting state or risk unintended changes. Preserve operation identity after uncertain effects and follow the existing recovery contract. Clean only positively owned disposable resources, and report unresolved cleanup. Human testing supplies no broader host-repair, production, paid-call or credential authority.

Check that results cover the artifacts proposed for acceptance. A later relevant behavior, command or environment change requires assessment of affected cases, not an automatic rerun of unrelated journeys. Close the qualification issue only on actual accepted human results for its required scope. Creating or closing another ticket cannot establish that those actions happened.

## Sources

[Microsoft's manual-case guidance](https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops) pairs actions with expected results and links tests to requirements. Its [execution guidance](https://learn.microsoft.com/en-us/azure/devops/test/run-manual-tests?view=azure-devops) distinguishes cases from runs against selected builds and configurations. [Diátaxis task guides](https://diataxis.fr/how-to-guides/) inform instructions written around the person's goal. These patterns do not require adopting a separate test-management platform.
