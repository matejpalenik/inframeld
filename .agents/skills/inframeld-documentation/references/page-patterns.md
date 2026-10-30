# Choose a page for the reader's purpose

Alice wants to try a feature, complete a task, understand a result or check a field. These are different reading situations. Choose a page purpose before writing. A feature does not automatically need four pages. A focused guide can link to an existing concept and reference rather than repeat them.

The [Diátaxis framework](https://diataxis.fr/) distinguishes tutorials, how-to guides, explanation and reference. Use the distinction to reduce friction, not as a requirement to create a large documentation tree.

## Tutorial: reach one supported first result

A tutorial teaches through a concrete path. State the result and required environment, identify the current permissions, then guide the reader from a known starting point to one observable result. Use realistic values consistently. Explain each necessary step without interrupting the path with every possible variation.

Show the smallest complete example first. Supply a file path, imports, execution command and expected result. End by explaining what the reader accomplished and where to go next. Include cleanup when the example creates resources. If cleanup can remove valuable data or fail after partial effects, explain its conditions.

Do not create an imaginary installation or publication story for convenience. The selected SDKs may be built from this repository without being published packages. The CLI may have an implemented command while a broader accepted command design remains future work. Inspect the supported interface and use its actual prerequisites.

## Task guide: solve a known problem

A task guide assumes that the reader knows the desired outcome. A useful flow is:

1. State the outcome and when this procedure applies.
2. Give the necessary prerequisites and retained context.
3. Perform the supported actions in dependency order.
4. Explain the result beside the action that produces it.
5. Address the failures that change the next decision.
6. Link to the next task or a deeper explanation.

Adapt these elements to the task. They are not compulsory headings. A three-step task does not need an artificial troubleshooting catalogue.

For original-request lookup, the prerequisites can include the original installation, scope, method, route, idempotency key, expected authority and a currently authorized credential. Inspect the actual interface before naming the fields. Explain which values are retained and which checks are current. Do not reconstruct original context from today's defaults. Cover every delivered observation outcome, including deliberately unresolved information, without inferring whether effects exist.

## Explanation: understand why behavior works this way

An explanation develops a mental model. Start with a small realistic situation and its purpose. Introduce concepts when the causal flow needs them. Explain ownership, normal behavior and changed state before unusual combinations. Show why an apparent shortcut would change a meaningful guarantee.

For example, explain that a lookup can protect private request history before describing why two different underlying cases may return the same unresolved result. Use the accepted owning reference for the rule. Keep internal component placement and persistence design in developer documentation unless they change what a user must do.

## Reference: find an exact contract

Reference is accurate, consistent and easy to scan. Group related fields and preserve exact names, types, required conditions and values. Distinguish omission from explicit `null`, and defaults from example choices. State bounds, relationships and current authorization where they affect validity.

Use native generated OpenAPI and generated client documentation as the source for exact HTTP and SDK shapes. A user page can explain a meaningful subset without duplicating a full manually maintained schema. A teaching JSON block is an example, not a replacement specification. Label an illustrative fragment so it cannot be mistaken for a complete request.

## Fit the maintained site

The Protocol App Router MDX pages are the source of user-facing documentation. Existing developer guides, domain references and ADRs retain their internal purposes. Link between them only where the intended reader benefits.

Add navigation only for pages that exist. Keep routes and heading anchors stable, and update internal links when a stock Protocol route is removed. Stock template paths are not Inframeld compatibility commitments. Avoid copying the same walkthrough into developer and user documentation. Keep a concise developer guide that explains implementation or verification differences, then link to the user task.

During delivery, return a changed-page manifest, source revision and verification evidence to the owning worker. Keep run status and review history in the external delivery record, not in a permanent user-facing progress inventory.
