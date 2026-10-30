---
name: inframeld-documentation
description: Write and review plain-language Inframeld user documentation and supported examples in the Protocol MDX application. Use for user guides, concepts and public interface reference, not internal architecture specifications or unrelated prose.
---

# Document a useful Inframeld outcome

Alice submits an access change and loses the response. A useful guide helps her find the retained result, understand what it establishes and choose a safe next step. Begin with that task before explaining the machinery behind it. Assume basic programming and terminal knowledge, but no prior knowledge of Inframeld.

Accepted domain references own behavior, inspected code owns implemented interfaces and native generated OpenAPI owns delivered HTTP shapes. Documentation explains these sources. It does not introduce new product contracts. Read only the owning workflow needed for the feature, then inspect exact interfaces before writing commands, fields, installation instructions or supported credential claims.

## Choose the page and evidence

Establish the reader, useful outcome, supported interface and exclusions from the authorized feature brief. Use [page patterns](references/page-patterns.md) to choose a tutorial, task guide, explanation or reference. An approved brief and reusable page pattern authorize routine composition. Do not request a new outline approval for every page. Raise material product or scope decisions, rather than inventing an answer.

For prose and explanatory flow, read [writing style](references/writing-style.md). For runnable snippets, language tabs and Protocol components, read [examples and MDX](references/examples-and-mdx.md). The [source observations](references/source-observations.md) explain the editorial evidence and its limits. They are our analysis, not an official OpenAI style manual.

## Write and verify

1. State what the reader can accomplish. Put necessary setup and current permissions before the first action.
2. Show the smallest supported path to a useful result. Explain the result immediately after the action that produces it.
3. Add failures where they affect a decision. Preserve uncertainty, partial effects, current authorization and documented retry rules. A timeout or unresolved lookup does not establish that nothing happened.
4. Add relevant alternatives and links after the main path. Keep internal component design in developer guidance.
5. Reconcile every public claim with the final implementation revision. Distinguish implemented behavior, accepted design and pending qualification.
6. Run `pnpm check:docs`, which includes the documentation build. Execute copyable examples against controlled fixtures when possible. A successful MDX build does not prove an HTTP request or provider action works. Report unavailable checks honestly.

Use [documentation maintenance](../../../docs/development/documentation-maintenance.md) for owning references, navigation and source changes. Avoid duplicating an exact schema already generated from OpenAPI. Do not promise commands, published SDK packages, application credentials or deployments that the inspected implementation does not provide.

## Coordinate edits

In a delivery run, follow the [assignment protocol](../inframeld-backlog-delivery/references/assignment-protocol.md) for checkout binding, trusted instructions and check/resource ownership. The worker owns Git operations. The documentation writer edits only the explicitly allocated user documentation paths and returns a manifest, implementation revision, source evidence and checks to that worker. Shared navigation has one named owner. Do not stage, commit, rebase or push from a writer assignment.

A user-visible change needs the relevant new or updated explanation and example. An internal-only change can record why no user page changes are needed. Preserve stable routes and anchors, use original Inframeld examples and remove template product claims. Apply the common prose rule of no semicolons or em dashes.
