---
name: Implementation capability
about: Deliver one concrete behavior with observable acceptance examples
title: ""
labels: "type:implementation"
assignees: ""
---

<!-- Read docs/development/documentation-maintenance.md#author-delivery-issues.
Use native GitHub parent and blocking relationships, not manual Ready/Blocked fields.
For a parent, specification or qualification, use the focused format in that guide.
Remove these instructions and replace every placeholder before publishing. -->

## Outcome

<What can Alice, Bob or SupportBot do when this ticket is delivered, and why?>

## Work

1. <A concrete action belonging to this ticket.>
2. <The next action, including a relevant failure boundary.>

## Acceptance examples

- <Given a concrete situation, what observable success is required?>
- <What is rejected, and what remains unchanged?>
- <If relevant, what happens after interruption, response loss or a competing change?>

## Boundaries

<Name adjacent work and its owning issues. Explain which prerequisite supplies a needed capability. Do not copy the prerequisite's implementation plan.>

## Read

- <Direct link to the owning workflow and relevant exact contract section.>
- <Matching pending decision when this work needs an unresolved answer.>

## Verification

<The behavioral tests or qualification evidence needed for these examples. Distinguish checks actually run from reported and pending evidence.>

Follow the shared Definition of Done at `docs/development/definition-of-done.md` in the current repository. Inspect current code before adding behavior that already exists. Keep work open until required implementation is merged and acceptance evidence exists.
