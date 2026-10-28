---
name: inframeld-rust-standards
description: Guides authored Rust in Inframeld for planning, suggestions, implementation and review, including CLI and xtask code. Covers Rust types, modules, errors, ownership, testing and presentation boundaries. Generated SDK source and generator maintenance remain with Rust SDK.
---

# Inframeld Rust standards

Use this skill with the [shared Coding Standards](../inframeld-coding-standards/SKILL.md) for authored Rust planning, suggestions, implementation and review, including tests and snippets. Follow applicable directory guidance. Loading guidance authorizes neither code edits nor publication.

Alice inspects a failed build through the CLI. A command handler requests permitted facts through the generated SDK and returns a typed result. The presenter formats those facts. Neither Rust types nor successful inspection establish that the build succeeded or that Alice may repeat it.

## Rust idioms and boundaries

- Group cohesive types, errors and functions in modules. Keep visibility private or `pub(crate)` until another crate needs an API. Rust does not inherit Python's one-primary-type-per-module, static utility-class, nominal Command/DTO or explicit Protocol-inheritance conventions.
- Prefer module functions for stateless operations and ordinary functions for command handlers. Put stateful behavior and invariants on the owning struct or enum. Use traits for real capability boundaries or multiple implementations rather than a trait, registry or command bus for every function.
- Model closed alternatives with enums and meaningful identity/invariant distinctions with newtypes. Keep passive result records simple. Preserve explicit unknown/absent values and avoid broad string maps or `serde_json::Value` as the default internal representation. Dynamic JSON remains appropriate at a deliberate untyped boundary.
- Make ownership, mutability and resource lifetime visible. Borrow inputs when ownership transfer is unnecessary. Use owned values when tasks or records need an independent lifetime. Do not add clones, reference counting or concurrency solely to satisfy a speculative architecture.
- Return `Result` for expected input, I/O, network and validation failures. Keep error classification typed where callers need to decide an outcome. Preserve useful causes without exposing credentials or raw protected values through `Debug`, `Display` or logs. One outer boundary owns final reporting and exit conversion.
- Production verification and integrity gates use explicit error paths. Ordinary assertions panic, and debug assertions may be omitted in optimized builds. Neither supplies the controlled error outcome required by these gates. Tests may use assertions and focused unwrap/expect allowances to fail on invalid fixtures without weakening production conventions.
- Keep asynchronous orchestration with the command/workflow owner. Bound external waits and preserve cancellation and resource cleanup. Renderers do not send requests, refresh credentials, authorize work or decide retry eligibility.
- Follow the [shared TDD and documentation contract](../inframeld-coding-standards/references/testing-and-documentation.md). Use process tests for real streams, exit codes, arguments and interaction behavior. Keep pure conversion/validation tests focused, and distinguish controlled SDK/HTTP evidence from real provider or persistence qualification.

The [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/) explain naming, conversions and API design. [The Rust book](https://doc.rust-lang.org/book/ch09-03-to-panic-or-not-to-panic.html) explains recoverable errors and test assertions. These are background references, not permission to override repository contracts or copy a general manual into this skill.

## Tooling and existing code

Use the pinned repository toolchain, Cargo lockfile and rustfmt. Apply strict compiler/Clippy checks and rustdoc diagnostics to authored code under the package's documented commands. Explain narrow exceptions rather than hiding broad warnings.

The existing [CLI manifest](../../../apps/cli/Cargo.toml) and [xtask manifest](../../../apps/cli/xtask/Cargo.toml) select denied compiler warnings, forbidden unsafe code, Clippy all/pedantic, and denied production unwrap, expect, panic, todo, unimplemented and debug macros. Preserve those package rules. Generated SDK code retains generator-owned settings, and another package's existing test/driver allowances are not silently migrated by this documentation.

The [Rust SDK skill](../inframeld-rust-sdk/SKILL.md) owns generated operations, transport defaults and regeneration. Use it for SDK consumption or maintenance. Do not add handwritten application HTTP calls, edit generated source or move backend rules into Rust to satisfy a command.

## CLI reading route

For command placement, clap declarations, typed results or the invocation lifecycle, read [CLI structure and presentation boundaries](references/cli-structure.md), accepted through ADR-0097. Keep command-specific declarations beside their handler, shared options at the root and final reporting under shared output. Small command inputs, execution, results and human views can share a module with distinct responsibilities.

For CLI dependency selection, shared output-component implementation, prompts, completions or presentation snapshots, read [Selected CLI libraries](references/cli-libraries.md), accepted through ADR-0096. Read Application Contracts' [shared presentation reference](../inframeld-application-contracts/references/cli-presentation-components.md) when component semantics or output behavior matter. A small Rust-only helper review does not require all CLI workflows.

Read [CLI directory guidance](../../../apps/cli/AGENTS.md) for local commands and implementation status. Accepted structure is distinct from implemented components. Exact command vocabulary, JSON schemas and mappings remain #156's work. Illustrative names do not select missing contracts or authorize application changes.
