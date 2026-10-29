# Give Rust components predictable responsibilities

Alice reports that discovery rejects her company's installation. A maintainer should find the discovery operation, inspect the trust decision and locate the provider transport without reading unrelated command parsing or terminal formatting. This reference standardizes those responsibilities. It does not require every capability to have the same files.

These are repository Rust conventions, refining the command-family design accepted under [ADR-0097](../../../../docs/adr/ADR-0097-organize-rust-cli-by-command-family-and-typed-results.md). The discovery capability and offline runtime use these boundaries. General product commands and shared presentation remain delivery work. Backend domains remain the owners of product authorization, transactions and resource state.

| Question | Read |
| --- | --- |
| What is fixed across the repository? | [Roles and dependency direction](#roles-and-dependency-direction) |
| Where does a small command go? | [Command adapter pattern](#command-adapter-pattern) |
| How does a larger capability split? | [Capability pattern](#capability-pattern) |
| Should this be an object or another crate? | [Choose a declaration and boundary](#choose-a-declaration-and-boundary) |
| What did established Rust projects teach us? | [Source-backed design lessons](#source-backed-design-lessons) |

## Roles and dependency direction

Onion architecture keeps decisions independent of replaceable details. Rust supports this through modules, ordinary data, methods and traits. A folder named `domain` cannot establish that direction by itself.

| Role | Owns | Does not own |
| --- | --- | --- |
| Composition/startup | Construct concrete resources and arrange shutdown. | Business decisions or formatting every outcome. |
| Command adapter | Translate command arguments and invocation policy into an operation. | A second implementation of backend permissions or retries. |
| Application operation | Coordinate a requested sequence, dependencies and typed outcome. | Terminal layout or arbitrary ambient credential selection. |
| Value/state owner | Represent meaningful identity, validity, state or owned resources. | Network calls hidden in conversion or formatting. |
| Pure policy | Decide from supplied facts and preserve rejection meaning. | Filesystem, environment, HTTP or terminal access. |
| External adapter | Translate SDK, protocol, filesystem or process behavior. | Decide product authority or hide uncertain effects behind success. |
| Presenter | Format permitted facts using shared output components. | Fetch missing facts, refresh credentials or retry a write. |

Composition knows concrete implementations. An operation receives the capabilities it actually needs. Pure policies and values do not import command parsing or presentation. External types stay at a deliberate boundary. Convert to owned application values when their semantics differ or an independent contract needs protection. Do not duplicate a maintained library's full metadata model merely to remove its name from an internal signature. Public SDK responses do not automatically become stable CLI JSON.

A custom trait is useful when the operation genuinely needs an implementation-independent capability. Existing `Read`, `Write`, iterators, concrete generated operations or an external library's required trait may already be the right seam. Do not create a forwarding gateway for every SDK operation to fill an architectural layer.

Do not require nominal Command/DTO pairs after every clap input. Introduce a distinct resolved-input or result type when validation, precedence or semantic meaning changes, rather than mechanically copying the same fields through another layer.

Visibility restricts which implementation details callers can use. It does not enforce the complete allowed dependency graph within one crate. Review direction manually. Do not add architecture/import tests to compensate, and do not split crates solely to manufacture a purity guarantee.

## Command adapter pattern

Use `commands/<family>/<operation>.rs` for ordinary product commands. Keep command-specific clap inputs beside execution and small typed results. A short human presenter may remain in that module with a distinct function. Shared reporting still owns representation selection, streams and final exit mapping.

For example, an inspection command translates its selector, calls the generated inspection operation and maps permitted facts. Adding a service object, protocol and mapper for that single forwarding sequence makes it harder to follow. Extract an application operation when there is meaningful orchestration, another real caller or independently reusable behavior.

Keep global argument groups at the root and family selection in the family module. The [CLI structure reference](cli-structure.md) owns the exact target layout, clap example and lifecycle diagram. A simple offline command may legitimately remain one small module. It does not need policy, domain, repository or adapter folders.

## Capability pattern

A substantial capability may combine a reusable operation, validated values, trust policies and external adaptation. Use a cohesive feature module and descriptive component filenames. Start with its public interface, then follow its operation into decisions and adapters.

| Component | Placement convention | Split when |
| --- | --- | --- |
| Feature interface | `<feature>/mod.rs` or the feature's root file. | The supported surface needs a readable facade over private implementation. |
| Application operation | A file named for the operation, such as `discover.rs`. | Orchestration obscures other independently changing responsibilities. |
| Value or state owner | A file named for its concept, such as `installation.rs`. | The invariant or resource lifetime deserves its own reading unit. |
| Policy | A descriptive `*_policy.rs` file. | A pure rule set is substantial or reused independently. |
| External adapter | A descriptive `*_transport.rs`, `*_store.rs` or protocol-specific file. | Protocol/I/O mechanics distract from the operation. |
| Failure contract | Beside the owning component or a feature error module. | Multiple feature components share a meaningful classification. |

These are predictable roles, not mandatory filenames or directory contents. One file owns one cohesive component, which may include its input, outcome, closely related errors and private helpers. Do not force one public type per file. Avoid generic `workflow.rs`, `models.rs` or `utils.rs` buckets when a component name would identify the owner more clearly.

The implemented capability under [`apps/cli/src/discovery/`](../../../../apps/cli/src/discovery/mod.rs) provides this reading map:

```text
discovery/
├── mod.rs                 Supported discovery interface
├── discover.rs            Bounded discovery operation
├── installation.rs        Discovery inputs, result and related profile types
├── url_policy.rs          API and issuer trust decisions
├── oidc_transport.rs      Provider HTTP adaptation and response limits
└── error.rs               Shared discovery failure classification
```

This is an inspected implementation, not a universal directory template. The public facade retains supported paths and a managed-local context with private fields. Provider requests are methods on the configured transport, while the ordered operation remains a function. The SDK, provider model, managed-local context and transport budget remain governed by the [discovery workflow](../../inframeld-application-contracts/references/cli-targets-and-accounts.md#target-discovery). A filesystem-only capability would have different adapters. Do not create an OIDC-shaped skeleton for it.

Keep helpers at the narrowest useful scope. Share within the capability before promoting into common infrastructure. Similar text does not prove equal policy. A raw connection parser and verified target discovery have different trust meanings even if both parse URLs. Share mechanical parsing only while preserving the distinct decisions.

## Choose a declaration and boundary

Use a function for stateless conversion, a pure decision or a short application operation. A module is already an encapsulation boundary. It need not contain an empty utility struct with only associated functions.

Use a struct or enum with methods when it owns meaningful state, dependencies, resources or invariants. Private fields and validated construction can make invalid combinations unavailable to ordinary callers. A configured transport used for several requests is a legitimate object. A private operation context can also keep shared state out of a long parameter chain while retaining a simple public function.

Avoid a public `Doer::new(...).execute()` ceremony when callers only need one function. Do not force an operation into an object solely to resemble Python. Conversely, do not turn a resource-owning object into unrelated free functions when methods make its lifetime and constraints clearer. [Types and boundaries](types-and-boundaries.md) covers the declarations and [the worked example](worked-verification-example.md) demonstrates a function using an existing standard-library capability.

Split a module when it mixes distinct reasons to change, hides the main operation behind helper machinery, exposes too much internals or has an independently useful policy/adapter. Lines are a review signal, not an architectural threshold. Avoid both a giant file and a maze of trivial forwarding modules.

Keep the CLI and xtask in their existing packages. Another crate needs an actual reuse, dependency, build or independently maintained API benefit. It brings a manifest, visibility and dependency maintenance cost. Keep async tasks, locks, registries, dependency injection containers and generic executors out of a design unless current behavior requires them.

Within a file, make the reading order intentional. Put module purpose and supported types/entry points where a newcomer can find them. Keep method implementations with their owner, private machinery after the supported interface, and unit tests in a test module or dedicated test child. Let rustfmt own mechanical formatting. No universal ordering rule should require jumping past the important operation just to read its contract.

## Source-backed design lessons

These inspected sources inform the conventions. They are not a popularity ranking or blanket endorsement. Their internal APIs evolve and their scale differs from this CLI.

| Source | Useful observed pattern | Limit on copying it |
| --- | --- | --- |
| [uv command families](https://github.com/astral-sh/uv/blob/main/crates/uv/src/commands/mod.rs) and [client components](https://github.com/astral-sh/uv/blob/main/crates/uv-client/src/lib.rs) | Feature entry points with focused reusable capabilities and private implementation modules. | Its many crates do not justify matching package count here. |
| [Cargo build command](https://github.com/rust-lang/cargo/blob/master/src/bin/cargo/commands/build.rs) and [library code map](https://github.com/rust-lang/cargo/blob/master/src/lib.rs) | A thin command invokes operations, with documented subsystem entry points. | Its build engine and global context are not a CLI framework to copy. |
| [ripgrep printers](https://github.com/BurntSushi/ripgrep/blob/master/crates/printer/src/lib.rs) | Separate human, JSON and summary components behind a small interface. | Its streaming JSON contract is not Inframeld's command envelope. |
| [Jujutsu command](https://github.com/jj-vcs/jj/blob/main/cli/src/commands/bookmark/create.rs) and [UI](https://github.com/jj-vcs/jj/blob/main/cli/src/ui.rs) | Command-local arguments and execution with shared presentation infrastructure. | Direct UI writes in a command do not supersede our typed-result reporting boundary. |
| [Deno entry point](https://github.com/denoland/deno/blob/main/cli/main.rs) and [tools](https://github.com/denoland/deno/blob/main/cli/tools/mod.rs) | Small executable and recognizable feature entry points. | Its runtime construction and task complexity solve a much larger problem. |
| [rust-analyzer architecture](https://rust-analyzer.github.io/book/contributing/architecture.html) and [style](https://rust-analyzer.github.io/book/contributing/style.html) | Explicit invariants, I/O boundaries, reader-oriented APIs and private context objects. | Do not import its compiler data model, assertion policy or every local style rule. |
| [Tokio source](https://github.com/tokio-rs/tokio/blob/master/tokio/src/lib.rs) and [clap source](https://github.com/clap-rs/clap/blob/main/src/lib.rs) | Capability documentation, examples and public-documentation checks. | We are not implementing another runtime or argument parser. |

The [Rust module guide](https://doc.rust-lang.org/book/ch07-02-defining-modules-to-control-scope-and-privacy.html) defines language privacy. [Rust's OOP discussion](https://doc.rust-lang.org/book/ch18-01-what-is-oo.html) explains structs, methods and encapsulation. Our component vocabulary and two patterns are repository policy informed by those capabilities, not an official universal Rust directory standard.
