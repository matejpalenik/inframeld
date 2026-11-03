---
name: inframeld-documentation
description: Write and review plain-language Inframeld user documentation and supported examples in the Protocol MDX application. Use for user guides, concepts and public interface reference, not internal architecture specifications or unrelated prose.
---

# Document a useful Inframeld outcome

Alice opens the documentation to install Inframeld or use an existing installation. Help her choose that path before introducing advanced recovery or machine output. Assume basic programming and terminal knowledge, with no prior Inframeld knowledge.

Accepted domain references own behavior, inspected code owns implemented interfaces and native generated OpenAPI owns delivered HTTP shapes. Read the relevant owning workflow and exact interfaces before claiming support for a command, field, credential or installation. Documentation explains the product without introducing contracts or turning accepted design into delivered functionality.

## Place the page

For new pages, moves and navigation changes, read [site structure](references/site-structure.md). Its approved hierarchy is mandatory: Get started, Product, Guides, CLI and SDKs, API reference, Self-hosting, and Changelog and support. Keep the defined labels and order. Detailed tasks belong under the appropriate entry, with shared setup in one canonical location. Preserve useful routes and anchors.

Establish the reader, useful outcome, page purpose, supported interface and navigation location from the authorized brief. Use [page patterns](references/page-patterns.md) to choose a tutorial, task guide, explanation or reference. Adapt headings to the task. A short version check needs neither a setup catalogue nor a troubleshooting manual. An approved brief and pattern authorize routine composition without another outline approval. Raise material scope or product decisions.

Read [writing style](references/writing-style.md) for prose and [examples and MDX](references/examples-and-mdx.md) for snippets, API views and rendering. [Source observations](references/source-observations.md) record editorial evidence and its limits, rather than an official OpenAI style manual.

## Write the useful path

1. Lead with what the reader can accomplish. Explain what an action does. Add a negative statement only when it changes a decision, prevents harm or corrects a likely misunderstanding.
2. Put necessary permissions, inputs and environment setup before the action. Link shared client setup. Include a prerequisites section only when it has useful requirements.
3. Show the smallest supported path and explain its result beside the action. Human CLI guides start with ordinary output. Put JSON, exit codes and automation contracts in their focused reference.
4. Offer CLI, cURL, Python, TypeScript and Rust alternatives where each interface actually supports the task. Keep identifiers, permissions and outcomes equivalent. Local version/configuration tasks need no fictional HTTP alternatives. Supply imports, lifecycle, created filenames and run commands for complete programs.
5. Preserve meaningful failures, current authorization, partial effects and retry rules. A timeout or unresolved lookup does not establish that nothing happened. Put conditions next to the action they constrain.
6. Reconcile claims with the final implementation revision. For an approved section whose capability is unfinished, give an honest availability page with a useful explanation and supported next steps. Never fill it with speculative commands, empty TODO tabs or public delivery logs.

Keep internal component design in developer guidance. Use original examples and no semicolons or em dashes in prose. Avoid competing schema tables or handwritten clients. The API reference reads the committed native contract through the maintained views. New delivered operations need a reference location and applicable examples.

## Verify and hand off

Run `pnpm check:docs`, including link/operation coverage checks and the production build. Check the reader path, navigation, code tabs, copy controls and narrow-screen layout. Execute copyable examples against controlled fixtures when possible. Report source checks, executed examples and unavailable visual/runtime checks separately. An MDX build proves neither a protected request nor a complete sign-in journey.

Use [documentation maintenance](../../../docs/development/documentation-maintenance.md) for owning sources. A user-visible change needs the relevant explanation and example. For a human-facing feature, prepare its linked [human-qualification procedure](../inframeld-testing/references/human-qualification.md) with commands, inputs, expected results and cleanup. The worker verifies the procedure and the coordinator publishes the issue. Writing it does not establish human acceptance.

During delivery, follow the [assignment protocol](../inframeld-backlog-delivery/references/assignment-protocol.md). Edit only allocated documentation paths and return a manifest, implementation revision, evidence and checks. The worker owns Git operations. A writer assignment does not authorize staging, committing or pushing. Shared navigation has one named owner.
