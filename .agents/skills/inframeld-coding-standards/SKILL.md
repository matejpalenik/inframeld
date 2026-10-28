---
name: inframeld-coding-standards
description: Guides shared engineering standards and language selection for Inframeld repository code planning, suggestions, implementation and review, including tests and snippets. Route Python and Rust to their language skills. Behavior-only tracing and documentation-only work do not require it merely because source is inspected.
---

# Inframeld shared coding standards

Help a developer make a change whose ownership, dependencies and failure behavior are easy to understand. Read this core before repository code planning, suggestions, additions, changes, refactoring or review, including test code and snippets. Select the language guidance below before proposing declarations or a file structure.

For example, Alice inspects a failed build. The CLI translates the requested operation and presents permitted facts, the backend owns build state and authorization, and a successful inspection remains distinct from successful build execution. Python services and Rust command handlers implement different responsibilities and need their own idioms.

Behaviour-only explanations, request tracing and documentation-only edits do not require Coding Standards merely because source is read. Loading any skill grants no write or external-action authority.

## Select the language and owner

| Work | Read next |
| --- | --- |
| Authored Python | [Python Standards](../inframeld-python-standards/SKILL.md). Backend work additionally follows its mandatory component references. |
| Authored Rust | [Rust Standards](../inframeld-rust-standards/SKILL.md), plus directory guidance. |
| Web or TypeScript | Existing [web guidance](../../../apps/web/AGENTS.md) and affected package/language guidance. No new TypeScript conventions are selected here. |
| Generated SDK source or generator behavior | The owning [Rust](../inframeld-rust-sdk/SKILL.md), [Python](../inframeld-python-sdk/SKILL.md) or [TypeScript SDK](../inframeld-typescript-sdk/SKILL.md) skill. Do not hand-edit generated output or impose authored-code rules on it. |
| Shared TDD, test/code documentation or examples | [Test behavior and explain the contract](references/testing-and-documentation.md). |
| Choosing test layers or interpreting evidence | [Testing](../inframeld-testing/SKILL.md), only when that strategy question arises. |

For a mixed-language change, load the affected language guides rather than all of them. Read the owning domain workflow when behavior matters. Before domain-specific backend design, generation or structural review, read that domain's architecture and relevant workflow. Shared backend components use [Application Contracts' component view](../inframeld-application-contracts/references/components-and-services.md), adding its transaction/job or gateway reference when applicable.

## Shared conventions

- Identify the owner, responsibility and dependency direction before choosing a declaration. Keep product rules with their owner. Transport adapters translate existing application behavior.
- Separate observations, decisions, representation conversion, persistence and resource lifetime. Preserve adapter integrity checks such as scope predicates, coordination locks, uniqueness, immutable bindings and conditional writes. Separation never removes those safeguards.
- Use meaningful types when identity, invariants, secrecy or accidental mixing matter. Avoid wrappers that add no meaning and broad untyped data containers that erase distinctions.
- Keep collaborators and resource ownership explicit. Bound external work and preserve the operation's original meaning after failure. Follow the owning retry/authorization contract instead of adding a new policy in a helper or renderer.
- Give each policy and representation one active owner. Share repeated decisions and presentation mechanics while keeping command-specific semantics explicit. Extract an abstraction when it supports real use, rather than pursuing a universal executor or framework.
- Preserve useful failures and safe diagnostics. Do not turn a failed operation into success because diagnostics or partial results were returned.
- Follow the shared [behavioral TDD and documentation contract](references/testing-and-documentation.md). Review organization manually, without architecture, naming, import-boundary or composition enforcement tests.

These principles do not select Python class patterns for Rust, impose backend layers on clients, or override frontend framework guidance. Domain and transport references own behavior. Language skills own declarations and implementation idioms.

## Suggest or review a change

1. Inspect the implemented contracts and distinguish accepted design, proposals and verification. Resolve only pending decisions triggered by this work through the [decision workflow](../../../docs/development/guides/architecture-decisions.md).
2. Choose the language, owner, narrow responsibility and affected dependencies. Load only the matching references.
3. Follow values from the external boundary to the owning behavior and back. Keep current authority, resource scope, state changes and failure meaning visible.
4. Apply the language's conventions. Show complete contextual examples with exact paths and placement when code is requested.
5. Verify the behavior at an appropriate boundary. Report checks actually run and material gaps. A documentation change does not migrate application code automatically.
