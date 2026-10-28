# ADR-0097: Organize the Rust CLI by command family and typed results

**Status:** Accepted

**Date:** 2026-10-28

## Context and Problem Statement

Alice inspects a failed build from a terminal or CI. A maintainer should be able to find that command's inputs, execution and result together, while shared presentation keeps the human and machine views consistent. Reading a failed build successfully is distinct from waiting for it to succeed.

The Rust CLI is a generated-SDK adapter with strict authored-code checks. Its library stack is accepted through ADR-0096. Its implementation currently provides offline help/version, explicit SDK construction and private packaging tooling. A maintainable source structure is needed before product commands grow.

## Considered Options

- Central technical directories for all arguments, handlers, results and presenters. Their categories are clear, while following one small command spreads across several trees.
- A multi-crate command-family structure following current uv. Compilation and API boundaries can support a large tool, with additional manifests, exports and dependency maintenance.
- Command-family modules within one CLI package, with shared context, client, interaction and output infrastructure. Related changes stay local, while common policy and mechanics have explicit owners.

## Decision Outcome

Select command-family modules within one CLI package with a small executable and library. On this date the developer accepted the complete proposal and requested detailed skill documentation and its lifecycle diagram. Application changes remain separately authorized work.

Keep global clap options and top-level selection at the root. Put family subcommands in the family module and command-specific declarations beside the handler. Compose one command tree for parsing, help, completions and manuals.

Keep small command arguments, execution, typed results and human presentation together as distinct responsibilities. Handlers call generated SDK operations and produce typed CLI-owned results. Shared reporting owns representation selection, controlled failures, streams and exit conversion. Renderers and progress sinks perform no product requests or retries.

The [Rust Standards structure reference](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md) owns placement, the worked clap example, lifecycle diagram, tooling and evolution guidance. [Application Contracts](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md) owns shared presentation responsibilities and links existing product semantics.

## Consequences

A command can be understood locally without repeating global formatting or interaction decisions. Some related declarations share a source file, requiring clear function responsibilities rather than a type-per-file rule. Modules split when substantial or independently reusable. Another crate requires a concrete reuse or compilation-boundary benefit.

This accepts a target structure, not public command vocabulary, JSON schemas or implemented presentation guarantees. Existing exact outcome, authority, dry-run and recovery rules remain with their owners. Dependencies, application migration and behavioral qualification remain delivery work. No command framework, competing HTTP client or structure-enforcement tests are introduced.

## Links

- [CLI structure and lifecycle](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md)
- [Shared presentation responsibilities](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md)
- [ADR-0096: selected CLI libraries](ADR-0096-select-reusable-rust-cli-presentation-libraries.md)
- [ADR-0055: CLI-first V1 through generated clients](ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md)
- [CLI implementation status](../../apps/cli/README.md)
