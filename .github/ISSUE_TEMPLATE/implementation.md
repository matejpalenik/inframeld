---
name: Implementation capability
about: Deliver one concrete behavior with observable acceptance examples
title: ""
labels: "type:implementation"
assignees: ""
---

<!-- Use .agents/skills/inframeld-issue-authoring/SKILL.md.
Use native GitHub parent and blocking relationships, not manual Ready/Blocked fields.
For another issue kind, use that skill's focused pattern.
Remove these instructions and replace every placeholder before publishing. -->

## Outcome

<What can Alice, Bob or SupportBot do when this ticket is delivered, and why?>

## Deliverables

1. <The complete capability this issue owns. List its endpoints, commands or other public interfaces when applicable.>
2. <The next owned behavior, including an important failure or recovery boundary.>

## Technical approach

<Explain the entry point, owning application/domain behavior, saved state and returned result. Name actual prerequisite capabilities and their producers. Identify proposed representations explicitly.>

<Where useful, add a small request/response example, operation diagram or illustrative pseudocode. Show relevant authority, transaction, retry and failure boundaries. Omit detail that does not apply.>

## Acceptance

- <Given a concrete situation, what observable success is required?>
- <What is rejected, and what remains unchanged?>
- <If relevant, what happens after interruption, response loss, changed permission or a competing change?>

## Verification

<The behavioral tests, integrations and qualification needed to establish acceptance. Distinguish planned verification from observed, reported or unavailable results.>

## References

- <Direct link to the owning workflow and relevant exact contract section.>
- <Matching pending decision when this work needs an unresolved answer.>

Apply the shared [Definition of Done](https://github.com/matejpalenik/inframeld/blob/main/docs/development/definition-of-done.md).
