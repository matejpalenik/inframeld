# Make Rust values, ownership and capabilities explicit

Alice downloads a CLI archive. A parsed checksum can establish that the expected text describes a SHA-256 value. Reading the archive and comparing its bytes establishes a different fact. Neither proves the download's publisher is trusted. Good types make these distinctions visible without wrapping every string or building a service hierarchy.

This reference owns authored Rust declaration choices. It does not redefine credential formats, public result schemas or generated SDK models. The [component reference](module-design.md) owns placement and the [complete example](worked-verification-example.md) shows values, conversion, a bounded read and an outer filesystem adapter together.

| Question | Read |
| --- | --- |
| Which facts deserve types? | [Values, records and alternatives](#values-records-and-alternatives) |
| Where should methods and traits go? | [Methods and capability contracts](#methods-and-capability-contracts) |
| When should values be borrowed or owned? | [Ownership and resource lifetime](#ownership-and-resource-lifetime) |
| How do failures and secrets cross boundaries? | [Errors and protected representations](#errors-and-protected-representations) |

## Values, records and alternatives

Use a newtype when mixing values would be harmful, construction establishes a real invariant or a protected representation needs controlled access. For example, a parsed digest differs from arbitrary text and a verified installation differs from an untrusted URL. A private field plus fallible construction can enforce the local invariant. It cannot establish current remote authority, permissions or future validity.

Choose standard conversions deliberately. `TryFrom` or `FromStr` can express validation. `From` should be infallible. Do not hide network requests, environment lookup, filesystem access or credential selection inside conversions. Use a named operation for those effects. The worked example's `ArtifactDigest::try_from` parses a complete digest and retains no invalid intermediate state.

Keep passive result records simple. Public fields are reasonable for an unconstrained record when callers may safely construct any combination. Fields enforcing an invariant remain private. Do not add getter/setter pairs to every record or require builder patterns for two required values. Use a builder when actual optional configuration or staged construction benefits from it. `Default` needs a meaningful safe default, not a fabricated identity or policy selection.

Use enums for closed alternatives, including distinct command outcomes and expected failures. Prefer a mode enum or separately named operation over opaque positional booleans. An `Option` records absence, while a `Result` records failure. Do not turn an unknown or not-yet-observed result into an empty success, zero count or false permission. Use an explicit unknown/partial/uncertain alternative when the owning contract distinguishes it.

Keep IDs, names and display labels distinct under the owning contract. A wrapper is useful when accidental interchange matters. It is unnecessary for every temporary string. Avoid `HashMap<String, String>` and `serde_json::Value` as internal substitutes for known structure. They remain valid for deliberately dynamic extension data or an untyped boundary. Do not invent stable CLI JSON by deriving `Serialize` on a vendor response.

Mapping is normally an ordinary function or a meaningful conversion implementation. Rust does not need Python's static mapper-class convention. A conversion with external effects is an operation, not a mapper.

## Methods and capability contracts

Rust structs and enums can combine data with methods through `impl`. Use that encapsulation when the component owns meaningful state, configuration, a resource or an invariant. Keep invariant-sensitive fields private and expose operations that preserve them. A configured provider transport, an owned child-process guard or a validated identifier has a clear reason to be an object.

A stateless policy or short operation can remain a function. Avoid empty utility classes and public objects constructed solely to perform one action. A private context object is valid when an operation needs shared implementation state. Do not expose that context simply to make the API look object-oriented. Prefer composition over attempting to reproduce class inheritance.

Traits describe capabilities. Use an existing standard trait when it expresses the boundary, such as `Read`, `Write`, `Iterator`, `TryFrom` or `Display`. Implement it explicitly with `impl Trait for Type`. Rust does not inherit Python's nominal Protocol base-class rules. Do not add a custom `ArtifactReader` trait if `Read` already describes the needed operation.

A custom trait can be justified even with one production implementation when it protects a real external boundary, supports meaningful controlled behavior or gives the caller an independent contract. Multiple real implementations and required library adapters are other valid reasons. A trait solely for naming, forwarding or a mocked constructor is not useful. The caller's needed capability determines the contract, not the full API of the concrete resource.

Choose concrete types, generics and trait objects by the actual caller and lifetime needs. `impl Read` is a small static-dispatch boundary. `&mut dyn Read` can avoid spreading generic parameters when runtime selection is sufficient. Do not parameterize every field or add associated types for imagined future backends. `Send`, `Sync`, `'static` and boxed futures should follow real task/library requirements, not be copied onto every trait.

External SDK/library traits are legitimate adapter boundaries. For example, the inspected [OIDC transport](../../../../apps/cli/src/discovery/oidc_transport.rs) implements the maintained library's async HTTP capability so the CLI can enforce its transport policy. That is different from inventing a trait per discovery helper. Actual application requests continue through generated operations, under the [Rust SDK skill](../../inframeld-rust-sdk/SKILL.md).

## Ownership and resource lifetime

Borrow inputs when callers retain ownership. Prefer semantic borrowed views such as `&str`, `&Path` and `&[T]` over `&String`, `&PathBuf` and `&Vec<T>` unless the owned container itself matters. Return owned values when the result must outlive an input or task. Avoid clones added solely to escape understanding a lifetime.

Sharing and copying must preserve meaning. `Copy` suits small independent values, not secret buffers or resource handles. `Clone` on a shared HTTP client may intentionally share its pool, while cloning a mutable credential or selection can create stale state. Explain the distinction where it affects correctness. Do not introduce `Arc<Mutex<_>>`, background tasks or asynchronous APIs into otherwise local work without an actual sharing or waiting requirement.

Make the resource owner clear. The component that opens a file or starts a child/task must account for its lifetime and failure path. A borrowed reader stays owned by the caller. An owned file closes through ordinary drop. Async cancellation drops a future, but does not automatically undo a remote write or terminate every detached child. Keep explicit cleanup and uncertain-effect reporting where the owning operation requires them. Avoid holding synchronous locks or SQL transactions across provider waits.

Use bounded reads, waits and process lifetimes at the external boundary that can enforce them. A byte limit is not a time limit. A request timeout is not a rollback guarantee. Do not introduce retries merely because an error looks transient. Preserve the backend's operation identity and retry contract.

## Errors and protected representations

Use `Result` for expected malformed input, unavailable resources, transport failures and controlled policy rejection. Keep variants typed when callers need to choose an exit, recovery action or representation. Use selected `thiserror` support for authored error contracts. Keep component-specific errors local until a caller needs a shared classification. Do not flatten everything to a string or create a giant application error enum for unrelated features.

Retain useful causes when safe. A path, upstream body, proxy credential or vendor error can become visible through `Debug`, `Display`, `source()` or a diagnostic library that traverses causes. If arbitrary causes are unsafe, retain an allowlisted status/category and document that boundary. Do not classify errors by searching their text. The worked example deliberately retains `io::ErrorKind` from an arbitrary reader and omits its uncontrolled message.

The outer reporting owner converts controlled outcomes to streams and exit codes. Inner values and errors do not print. Failure to verify remains failure even if diagnostic facts exist. Verification gates must return an error, not use `assert!` or `debug_assert!`. Preserve existing production bans on unwrap, expect, panic, todo, unimplemented and debug macros. Tests can use focused allowances and assertions to reject invalid fixtures.

Protect secrets across every representation, not only user-facing output. Do not derive `Debug`, `Serialize`, `Display` or `Clone` blindly on credential-bearing values. The following original teaching example is a complete illustrative new file at `apps/cli/src/sensitive_text.rs`. It is not an installed credential type or a replacement for Access's storage and zeroization requirements.

```rust
//! Prevent accidental debug disclosure of explicitly sensitive text.

use std::fmt;

/// Text that requires deliberate access at a trusted boundary.
///
/// Debug output is redacted. This wrapper does not validate a credential,
/// encrypt memory or guarantee that the allocation is erased when dropped.
pub(crate) struct SensitiveText(String);

impl SensitiveText {
    /// Take ownership without copying or interpreting the text.
    #[must_use]
    pub(crate) fn new(value: String) -> Self {
        Self(value)
    }

    /// Borrow the protected text for an explicitly trusted operation.
    #[must_use]
    pub(crate) fn expose(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for SensitiveText {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("SensitiveText([REDACTED])")
    }
}
```

The object owns a representation boundary and exposes one intentional borrowing operation. It is not a stateless utility class. There is no `Display`, serialization or automatic cloning to create additional disclosure paths. The caller still must not log `expose()` or an HTTP request containing it. Rustdoc explains the protection's exact limit rather than claiming general secret safety.

For behavior tests, use a sentinel secret and confirm that debug/error output excludes it while deliberate access still returns the original text. A type/field naming test would not demonstrate this protection. Real credential storage, refresh, secure persistence and remote trust remain their owning Access contracts.

## Sources and application limits

The [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/) cover conversions, predictability, flexibility and type safety. The [Rust book on recoverable errors](https://doc.rust-lang.org/book/ch09-03-to-panic-or-not-to-panic.html) explains the distinction between `Result` and panic behavior. The [Rust book](https://doc.rust-lang.org/book/ch18-01-what-is-oo.html) explains encapsulation, and [rust-analyzer's style guide](https://rust-analyzer.github.io/book/contributing/style.html) supplies concrete examples of invariant-sensitive fields, borrowed views, private contexts and avoiding public doer objects. These inform the conventions without importing every project-specific rule.
