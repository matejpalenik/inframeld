# Document Rust for the person changing it

Alice sees a discovery error. The next maintainer needs to know which public facts discovery validates, which network requests it performs and whether it changes saved credentials. A comment repeating its Rust return type cannot answer those questions. This reference owns authored Rust rustdoc conventions. The shared [documentation contract](../../inframeld-coding-standards/references/testing-and-documentation.md) retains purpose-first writing, complete examples and behavioral TDD.

| Question | Read |
| --- | --- |
| Which comment form belongs here? | [Document the right scope](#document-the-right-scope) |
| What should an operation explain? | [Write the component contract](#write-the-component-contract) |
| How detailed should examples be? | [Examples that teach and remain valid](#examples-that-teach-and-remain-valid) |
| Which checks can we rely on? | [Check documentation without manufacturing prose](#check-documentation-without-manufacturing-prose) |

## Document the right scope

Use `//!` for the containing module or crate and `///` for the following type, function, method or field. Use ordinary `//` comments for implementation reasoning, ordering and non-obvious local constraints. Rustdoc is available through editor documentation and generated HTML, so it should explain the supported behavior rather than narrate the source.

| Scope | Explain | Avoid |
| --- | --- | --- |
| Crate or substantial module | Purpose, owner, entry point, main collaborators and boundaries. | A second architecture manual or a list of filenames without responsibilities. |
| Meaningful struct or enum | What it represents or owns, invariants and what constructing it establishes. | Restating field types or claiming runtime authority from a type. |
| Public/important internal operation | Requested behavior, prerequisites, effects, result meaning and relevant failures. | A blanket argument/return template duplicating the signature. |
| Policy or adapter | The decision or external boundary, important assumptions and rejection. | Calling all failures generic transport problems without meaningful distinctions. |
| Private helper | Non-obvious rationale, assumptions or meaningful contract. | Mandatory prose for obvious arithmetic or ordinary propagation. |
| Test or fixture | Scenario, meaningful controlled conditions and what evidence it establishes. | Repeating every assertion or documenting test naming rules as behavior. |

Document every reachable public authored API. Also explain meaningful internal components and entry points even when `pub(crate)` or private. This is an editorial requirement based on reader needs, not a requirement for long documentation on every declaration. Closely related fields can be explained once in their owning type when their meaning is already clear. Explain units, absence, trust or lifecycle distinctions where names and types are insufficient.

A trait owns the shared capability contract, including failure and ownership expectations. Implementations add concrete behavior or meaningful differences. Standard trait implementations do not need to repeat the standard library manual. Inherent methods own their supported semantics. Keep implementation details in comments or module documentation when callers do not need them.

## Write the component contract

Start with a concise, complete sentence explaining the component's purpose. The first paragraph appears in rustdoc summaries, so a reader should understand why to use it without parsing a dense term such as first-party metadata transport adapter. Explain an unfamiliar term where it changes the reader's understanding.

Then add only relevant context:

- What is supplied and what has already been checked. Clarify canonical spelling, units, ownership or currentness when relevant.
- What the component reads, writes, starts or reveals. Include important negative guarantees such as never loading saved credentials when they define the trust boundary.
- What successful output establishes, and what remains unverified. Matching a digest is not publisher authentication. Inspecting a failed job is not waiting for success.
- Relevant failure, cancellation, ordering and changed-state behavior. A timeout after a write may mean uncertainty rather than no effect.

Use these conventional sections when applicable, without empty template headings:

| Section | Use |
| --- | --- |
| `# Errors` | Conditions and meaningful error distinctions for a fallible operation. Link the owning error type when useful. Do not list every transitive vendor error. |
| `# Panics` | Actual reachable panic preconditions that callers must understand. Do not add hypothetical panics from arbitrary caller implementations. Our production integrity checks still require controlled errors. |
| `# Safety` | The caller's contract for an unsafe API. It is not a general HTTPS/security section, and authored CLI/xtask code currently forbids unsafe code. |
| `# Examples` | A small meaningful use, result or failure. One example can serve related items through links. |
| `# Cancellation`, `# Limits` or effects prose | Add when timing, resource bounds, partial effects or caller resource reuse require explanation. These custom sections are not mandatory everywhere. |

Use intra-doc links such as ``[`ArtifactDigest`]`` and ``[`verify_reader`]`` to supported symbols. Format Rust symbols as inline code in prose and inside links, including error variants such as ``[`VerificationError::TooLarge`]``. Bare symbolic link labels can also fail the existing Clippy `doc_markdown` check, so rustdoc generation alone is not the complete documentation check. Keep public docs valid without requiring private-item output. Link external provider standards or a maintained guide for extended rationale instead of embedding copied manuals. Preserve one active owner for each rule. Domain references and ADRs own product decisions, while code documentation explains the implemented contract.

The following original teaching excerpt illustrates the public contract documented on `discover` in [`apps/cli/src/discovery/mod.rs`](../../../../apps/cli/src/discovery/mod.rs). It is a shortened explanation, not a copyable replacement or a proposed source change. The source owns the complete current rustdoc and compiling example.

```rust
/// Validates an installation's public identity and login configuration.
///
/// Use this before offering to save a remote target. The supplied API URL
/// must exactly match the resource identity advertised by the server.
///
/// Reads application metadata, identity-provider metadata and public signing
/// keys. It does not load saved credentials, save a target or start login.
///
/// # Limits
/// Discovery allows ten seconds overall, five seconds per request and
/// 64 KiB per response. Redirects and automatic retries are disabled.
///
/// # Errors
/// Rejects invalid URLs, mismatched identities and unsupported login profiles.
/// Network, certificate, timeout and metadata failures return safe categories
/// without exposing upstream response bodies.
```

The limits above reflect the inspected discovery implementation. If behavior changes, update this contract and the owning workflow together. Do not copy these exact network limits onto unrelated operations. The complete [artifact example](worked-verification-example.md) shows a module introduction, typed values, errors, a callable operation and a deterministic doctest in context.

## Examples that teach and remain valid

Prefer original, small examples tailored to the repository. If using upstream code, identify its exact repository path, source and excerpt scope. Preserve necessary checks and explain which incidental choices are not local rules. Respect source licensing and quotation limits. Link to large examples rather than copying them. The [module-design sources](module-design.md#source-backed-design-lessons) record the patterns that informed the original worked example.

For every proposed source snippet, name its exact destination and whether it is a complete new file, replacement or insertion. Include imports and context needed to use it. Label teaching excerpts and pseudocode explicitly. A function with an omitted body is not a complete implementation. Separate multi-file examples and explain their connection. Example declarations do not authorize application edits or create missing product commands.

Make examples show a useful behavior or invariant. Prefer `?` for fallible production-style usage. Reserve unwrap/expect for focused test code with the package's test-only allowance. Assertions are useful in deterministic doctests to show an outcome, while production qualification still returns explicit errors.

Run deterministic examples as doctests. Use `no_run` when a useful example genuinely needs an external server, interactive input or another environment prerequisite. It compiles without contacting that service. Do not use `ignore` to conceal broken code. Hidden `#` setup can provide a complete Result-returning context without cluttering rendered docs, but must not hide important trust checks. Private implementation tests belong in unit tests rather than widening the API so a doctest can reach it.

Do not require an example on every trivial getter, enum variant or alias. An example on the owning operation with links from its types is often enough. No rustdoc example may use real credentials, contact paid models or imply that a fabricated command exists.

Keep source examples, human guides and tests consistent without making three competing specifications. Rustdoc explains components. A feature's manual CLI recipe explains prerequisites, real commands, expected observations and cleanup under [CLI directory guidance](../../../../apps/cli/AGENTS.md#manual-feature-verification). Automated checks do not substitute for an unexecuted manual journey. A library-only feature must state that the executable does not yet expose it.

## Check documentation without manufacturing prose

For new or changed authored public APIs, missing documentation is a defect. Retain strict rustdoc warnings and broken-link checks. When implementation work configures `missing_docs`, apply it to authored crates and assess actual public exports. It does not check every meaningful private component, explain prose quality or justify making private items public. Do not impose a blanket private-item documentation lint that produces filler.

Both authored CLI and xtask manifests deny `missing_docs`. Local and CI rustdoc checks include all features with `RUSTDOCFLAGS='-D warnings'`, alongside strict Clippy and doctests. This checks reachable public documentation and valid links, not prose quality or every private component. Private-item documentation remains available for developer inspection. Generated SDK settings stay generator-owned.

From the repository root, this is a supported inspection command using Cargo's private-item documentation option:

```sh
RUSTDOCFLAGS='-D warnings' cargo doc --locked -p inframeld-cli -p inframeld-cli-xtask --all-features --no-deps --document-private-items
```

Run doctests through the affected package's normal checks. Generating HTML does not execute the examples. `no_run` verifies compilation only. Neither successful rustdoc nor lint establishes remote provider behavior or release qualification.

Review whether a new reader can identify the owner, requested behavior, effects, failures and relevant limits. Check links and example fidelity after changes. Do not add tests that merely match comment wording, filenames or module structure. The shared behavioral TDD contract continues to govern real behavior tests.

## Sources

- [Rustdoc introduction](https://doc.rust-lang.org/rustdoc/what-is-rustdoc.html) defines item and module documentation.
- [Writing documentation](https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html) explains concise summaries, contextual explanations and examples.
- [Rust API documentation guidelines](https://rust-lang.github.io/api-guidelines/documentation.html) covers examples, failure sections and links, with proportional application.
- [Documentation tests](https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html) explains executable examples, hidden setup and compile-only examples.
- [Rustdoc lints](https://doc.rust-lang.org/rustdoc/lints.html) and [private-item output](https://doc.rust-lang.org/rustdoc/command-line-arguments.html#--document-private-items-show-items-that-are-not-public) define the checks and their limits.
