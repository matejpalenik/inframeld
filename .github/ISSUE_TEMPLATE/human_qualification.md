---
name: Human qualification
about: Check one human-facing feature through a supported user journey
title: "Human acceptance: "
labels: "type:qualification"
assignees: ""
---

<!-- Follow docs/development/documentation-maintenance.md#author-delivery-issues
and .agents/skills/inframeld-testing/references/human-qualification.md.
Replace these instructions with feature-specific content before publication.
If a capability or command is unavailable, explain the exact gap and its owner.
For deferred testing, replace not-yet-ready sections with named outstanding work
and its owner. Complete them before human handoff. Do not invent runnable
instructions or hand an incomplete procedure to a human. -->

## Outcome

Describe what the person should accomplish and why, using a small example. Link the feature issue and relevant implementation PRs. State what this qualification covers and excludes.

## Deferred human work and timing

For automated backlog delivery, identify the human observations deferred to pre-v1 testing. Link available implementation/artifact references and automated evidence. Name the owner and prerequisites for remaining manual setup, artifact selection, procedure preparation and its engineering dry run. Those manual tasks may remain pending when implementation closes under the delivery policy.

Keep this issue open until actual accepted human results exist. An incomplete procedure is not ready for human handoff. Missing product behavior and required automated checks remain with their owning implementation or automated-qualification issues.

## Prerequisites and starting state

Identify the required capabilities and their owning issues or delivered PRs. Use native GitHub blockers for unresolved implementation prerequisites.

Before human handoff, specify:

- Exact backend, UI and client artifacts to test.
- Supported platform and browser where relevant.
- Verified installation/start commands, working directories and browser URLs.
- Test accounts, permissions and initial data, with safe reset instructions.
- Where each required identifier, input and expected value comes from.

If something is unavailable, name the missing capability and engineering owner. Do not ask the tester to discover setup, construct credentials or infer values.

## Engineering readiness before human handoff

- [ ] Required capabilities are delivered in the selected artifacts.
- [ ] Setup, test data and cleanup instructions are complete.
- [ ] Commands, URLs and UI actions match the delivered interfaces.
- [ ] Expected outputs and failure behavior have been checked.
- [ ] An engineer followed the complete procedure successfully and recorded the artifacts and result.
- [ ] Known limitations and required human observations are explicit.

An engineering dry run does not replace human acceptance. These readiness items may remain pending during automated implementation delivery. Leave unavailable items unchecked and explain their owner. Complete them before human handoff. No placeholder procedure is ready.

## Test procedure

Give each distinct workflow its own case and starting state. Use literal commands and actual UI labels. Explain dynamic output fields and their expected values. Link a maintained walkthrough for shared setup rather than copying it.

| Step | Exact action, command or UI interaction | Expected result |
| --- | --- | --- |
| 1 | Specify the action, working directory and required inputs. | Specify the observable result. |
| 2 | Specify the next action. | Include relevant output, exit status or unchanged state. |

## Relevant alternatives and recovery

Provide concrete procedures for applicable cancellation, rejection and recovery cases. State how each case starts from the required state. Link existing automated evidence separately. It does not establish an unexecuted human journey.

## Cleanup

Give the exact supported cleanup procedure and explain what it removes. Identify what to do if cleanup cannot be confirmed. Use only the disposable test resources.

## Execution records

Record shared qualification details once in this ticket:

- Tested artifact revisions.
- Failure-injection method, or `Not applicable` when none was used.

Reference these details from each run and record changes rather than overwriting earlier evidence.

Record each execution in a separate comment, preserving the reusable procedure:

- Tester and date.
- Artifact selection, platform and configuration, with any differences from the shared details.
- Case and failed or blocked step, if any.
- Expected and actual result.
- Passed, Failed, Blocked or Not run for each required case.
- Redacted evidence and linked defects.

Do not attach credentials or protected authentication captures. These are test outcomes, not a second implementation-dependency status system.

## Completion

Close only after the required cases have actual accepted human results. An incomplete procedure, missing capability or passing automated suite is not a passing human test. Record any explicitly approved scope change or deferral and its remaining owner without claiming that the omitted journey was verified.
