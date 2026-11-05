---
name: inframeld-issue-authoring
description: Write, review or restructure Inframeld GitHub issues and their scope or dependencies. Use for issue authoring and backlog reconciliation, not ordinary implementation or delivery coordination.
---

# Write issues an engineer can finish

Alice needs to grant Bob permission on Support. An issue should explain the supported operation, its owner, what is saved and returned, and the tests that prove it works. It should let an engineer begin without reconstructing a delivery chat or inventing the architecture.

This skill owns issue content and authoring. Domain references own accepted behavior, code and generated OpenAPI own implemented interfaces, and migrations own stored representations. [Testing](../inframeld-testing/SKILL.md) owns qualification. [Backlog Delivery](../inframeld-backlog-delivery/SKILL.md) owns assignment, execution and closure. Drafting or loading this skill grants no publication, implementation, messaging or Goal authority.

## Choose the writing route

- For a feature, defect, epic, specification, qualification or deferred issue, read [issue patterns](references/issue-patterns.md). Use the [implementation template](../../../.github/ISSUE_TEMPLATE/implementation.md) for an implementation leaf. The patterns adapt its structure to other kinds of work.
- For a split, transfer, dependency repair or bulk rewrite, also read [backlog restructuring](references/backlog-restructuring.md). Preserve every requirement and its receiving owner before changing the graph.
- For human qualification, use the [existing template](../../../.github/ISSUE_TEMPLATE/human_qualification.md) and [Testing's procedure](../inframeld-testing/references/human-qualification.md). Keep human observations distinct from implementation and required automated acceptance.

## Establish the outcome and its owner

Read the issue, relevant comments, parent, actual blockers and associated PRs. Identify the smallest coherent accepted outcome and compare it with the owning workflow, exact contract and relevant ADR. Use [Architecture](../inframeld-architecture/SKILL.md) when the outcome crosses owners or its v1 boundary is unclear. Read only the domain and contract sections that govern the work. Apply Coding Standards and its language guidance when suggesting repository code.

Keep accepted design, proposed implementation, inspected delivery, verified results and deferred work distinguishable. Follow explicit supersession. Surface a genuine unresolved choice before publishing affected requirements. Never infer a new permission, endpoint, provider guarantee or schema merely to complete a template. An approved issue rewrite does not itself accept a new product policy.

## Give enough technical direction

Use a realistic example, concrete deliverables, a focused technical approach and observable acceptance. List the endpoints, commands or other public interfaces owned by the issue when applicable. Explain relevant authorization, persistence, transaction, retry and failure boundaries. Show request/response examples and small operation diagrams when they clarify those decisions. Label proposed representations and illustrative code. Do not force API diagrams onto storage, documentation or qualification work.

Link a short route to current authoritative sections rather than copying global conventions or a field catalogue. State a required producer capability and its owner. Use native parents for decomposition and blockers for actual prerequisites, without duplicate Ready/Blocked fields. Keep issues stable through code reorganization and omit dated checkout inventories, generic process reminders and unrelated adjacent-work commentary.

Before returning or publishing, check that the engineer can identify the complete outcome, owned effects, actual inputs, rejection behavior and decisive verification. Preserve useful partial-delivery evidence without claiming completion. [Definition of Done](../../../docs/development/definition-of-done.md) remains the shared completion contract.

## Publish within the actual grant

Use existing issues before creating replacements. Preserve comments and closed historical scope/results. Re-read current issue content before an authorized edit, reconcile intervening changes and read back the result. If publication is not authorized, return the draft and proposed relationships. If an effect is uncertain, inspect it before repeating it. Report unresolved decisions and remaining acceptance plainly.
