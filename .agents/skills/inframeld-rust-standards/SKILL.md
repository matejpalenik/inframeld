---
name: inframeld-rust-standards
description: Guides authored Rust planning, implementation and review in Inframeld, including CLI and xtask code. Covers component structure, types, ownership, errors, documentation and tests. Generated SDK maintenance belongs to Rust SDK.
---

# Inframeld Rust standards

Use with [shared Coding Standards](../inframeld-coding-standards/SKILL.md) for repository Rust work, including suggestions, tests and snippets. Follow affected directory guidance. Behaviour tracing or documentation-only work does not require code review merely because Rust source is inspected. Loading this skill grants no edit or external-action authority.

Alice inspects a failed build. The CLI requests permitted facts through the generated SDK, produces a typed outcome and presents it. Successful inspection does not mean the build succeeded. A maintainer should find that command, understand its dependencies and follow its failures without reconstructing a framework.

## Essential standards

- Organize by command family or cohesive capability. Give operations, values, policies, adapters and presentation explicit owners. Apply inward dependency rules without reproducing backend domains or requiring identical Onion directories in every feature. One component may include closely related types and helpers. No type-per-file mandate, empty layers, command bus or registry for a closed command enum.
- Use functions for stateless work. Put owned resources, meaningful state and invariants on structs or enums with methods. Traits express real capability contracts or external-library requirements, not a mandatory interface for each function. Prefer composition to simulated class inheritance and public one-action service objects.
- Use enums for closed alternatives and newtypes where identity, validity or secrecy matters. Keep passive records simple and unknown values explicit. Avoid untyped string maps or `serde_json::Value` as the default internal representation. Deliberate untyped boundaries remain valid.
- Borrow when ownership transfer is unnecessary. Own values when their lifetime requires it. Keep mutability and resource cleanup explicit. Do not add clones, `Arc`, locks, tasks or generics for speculative flexibility.
- Return typed `Result` failures for expected validation, I/O and network outcomes. Preserve useful safe causes. Protect `Debug`, `Display`, serialization and logs from credentials or upstream protected content. The outer reporting boundary owns streams and exit conversion.
- Integrity and verification gates require explicit error paths. Production assertions can panic, and debug assertions can disappear. Tests may use focused assertion and unwrap/expect allowances without weakening production rules.
- Bound external waits and retain cancellation and cleanup meaning. Keep async orchestration with the operation owner. Renderers do not send requests, refresh credentials, authorize work or decide retry eligibility.
- Explain meaningful components in purpose-first rustdoc, including important internal components. Document effects, invariants, result meaning and relevant failures. Avoid blanket comments on obvious helpers and repeated signature descriptions. Preserve the shared [TDD and documentation contract](../inframeld-coding-standards/references/testing-and-documentation.md).

## Read the affected reference

Read only the rows needed for the task. Detailed references own the complete conventions and exceptions.

| Task | Read |
| --- | --- |
| Choose module boundaries, files, functions or objects, or review architecture | [Component roles and module design](references/module-design.md). |
| Design values, enums, ownership, traits, conversions or safe errors | [Types, ownership and capability boundaries](references/types-and-boundaries.md). |
| Write or review rustdoc, examples, test documentation or documentation checks | [Document Rust for its readers](references/documentation.md). |
| Build or review a complete bounded operation with typed values and I/O | [Worked artifact-verification example](references/worked-verification-example.md), an original teaching example, not application delivery. |
| Place commands, compose clap declarations, map results or follow an invocation | [CLI structure and lifecycle](references/cli-structure.md), accepted under ADR-0097. |
| Implement shared presentation, prompts, completions or snapshots | [Selected CLI libraries](references/cli-libraries.md), accepted under ADR-0096, and Application Contracts' [shared presentation rules](../inframeld-application-contracts/references/cli-presentation-components.md) when semantics matter. |
| Consume or maintain the generated Rust SDK | [Rust SDK](../inframeld-rust-sdk/SKILL.md). Generated operations and source remain generator-owned. |

For a narrow helper, do not automatically load every CLI workflow. Read the owning domain contract when its behavior matters. Application Contracts owns the accepted [common machine framing](../inframeld-application-contracts/references/cli-output-and-automation.md) and invocation rules. Feature-command vocabulary, typed leaf payloads and runtime integration remain their owning delivery work. Teaching examples establish no missing public contract.

## Implement and verify

Inspect existing consumers and explain the component's owner before changing its interface. Keep modules private or narrowly visible until an actual consumer needs more. Application requests use the generated SDK, with no competing handwritten endpoint client or client-side copy of backend authorization.

Use the pinned toolchain, Cargo.lock and rustfmt. Preserve the [CLI](../../../apps/cli/Cargo.toml) and [xtask](../../../apps/cli/xtask/Cargo.toml) rules, including forbidden unsafe code, denied warnings and missing public documentation, Clippy all/pedantic and production unwrap, expect, panic, todo, unimplemented and debug macros. Explain narrow exceptions. Generated SDK and other native-driver allowances are not silently migrated.

Follow behavioral TDD and verify observable behavior. Process tests own arguments, streams, exits and interaction. Controlled HTTP evidence differs from real provider, persistence and platform qualification. Do not add architecture, naming, import-boundary or composition-construction enforcement tests.

At handoff, follow [CLI directory guidance](../../../apps/cli/AGENTS.md) for manual feature verification and identify library-only delivery honestly. Report actual checks and gaps. Standards describe required practice, while manifests, inspected code and executed evidence establish implementation.
