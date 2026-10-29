# Server discovery verification

Issue #118 adds anonymous installation discovery and a stateless Rust consumer. [ADR-0098](../../adr/ADR-0098-publish-bounded-first-party-discovery.md) records the accepted contract. The [operator guide](../guides/server-discovery.md) explains configuration. This report records personally executed local checks separately from pending CI.

## Implementation boundary

The backend publishes the root and path forms of RFC 9728 metadata. Its allowlist contains the canonical API resource, one issuer, the API scope, header bearer transport, profile version, persistent installation UUID and fixed public client ID. Startup reads the existing identity. Missing identity and inconsistent enabled configuration fail startup. Disabled discovery returns a safe 503. Host and forwarded headers cannot change the published identity.

The Rust library uses fresh generated SDK calls for application metadata and `openidconnect` 4.0.1 for provider metadata and key-set parsing. It saves no targets and reads no login credentials. Verified HTTPS is the ordinary transport. Additional trusted CAs and explicit proxies are supported. An internal managed-local context requires recorded literal-loopback origins and installation identity. It has no public constructor or deserialization path. Its actual trusted creation remains #162. Saved targets and login remain #159 and #160.

Discovery has a ten-second overall deadline, five seconds per request and a 64 KiB body limit at each hop. It does not follow redirects or retry. Provider and key-set requests cannot leave the selected issuer origin. Successful discovery does not qualify a complete OAuth login or release compatibility.

## Behavioral evidence

The backend tests cover anonymous access, exact field disclosure, request-header independence, canonical root and prefixed resources, disabled publication, invalid configuration, accidentally advertised configured admin endpoints and clearing a prior identity snapshot after reload failure. Native PostgreSQL tests cover identity preservation across resource restarts and refusal to replace a missing identity. A real Hydra test independently compares the published projection with provider metadata and the registered client.

Ten Rust tests exercise verified local HTTPS, separate API and issuer origins, root and prefixed paths, verified HTTPS CONNECT proxy use, managed-local proxy rejection, managed-local identity and origin restrictions, malformed and hostile metadata, redirects at all three hops, API and key-set body limits, unsupported PKCE and grant capabilities, foreign protocol/key-set endpoints, untrusted/expired/wrong-host certificates, request and total deadlines, and cancellation without retry. Failure messages exclude injected private response text. Request observations verify the absence of authorization and cookie headers. Short private test budgets exercise deadline behavior without adding public timeout configuration or five-second waits to fast tests.

Scaffold-first runs observed the intended backend and Rust behavioral failures before implementation. Cross-language qualification additionally found three test-support defects. The witness decoded escaped wire paths, the discovery fixture used a nonstandard UUID, and the Rust socket probe read accepted nonblocking sockets as though they were blocking. A failing wire-path regression preceded its correction. The UUID fixture and socket mode were corrected while preserving SDK parsing, path assertions and transport deadlines. Native Rust lifecycle regressions then passed all five cases.

Architectural review subsequently reproduced four independent failures: malformed URL authority syntax, single-segment encoding of nested discovery paths, managed HTTP forwarding through a proxy and acceptance of incompatible grants. Those regressions now cover anchored authority checks, fixed wire targets, managed proxy rejection and the required authorization-code/refresh profile. Omitted grant metadata uses the standard authorization-code/implicit default and fails the refresh requirement.

[ADR-0099](../../adr/ADR-0099-preserve-encoded-relative-paths-in-generated-clients.md) records the annotated encoded-path capability. The Rust caller passes its encoded URL path directly. All selected generators preserve separators and existing escapes without changing ordinary path parameters. Independent predetermined metadata and raw target assertions cover nested paths, trailing slashes, spaces, encoded slashes and percent signs. Native Rust, TypeScript and Python sync/async regressions verify malformed arguments produce no dispatch. A coverage regression preserves unrelated parameter references. The four original architectural-review probes were rerun against a fresh copy of the final Rust source and all passed.

Final consistency tests also observed failures for malformed percent escapes before backend and Rust URL validation were aligned. The new checks reject these values before SDK transport or publication. No public timeout/proxy-bypass flag or dependency was added.

## Local results before the Rust structure refactor

The issue implementation was tested before the Rust structure refactor below, on macOS arm64 with the pinned Node, pnpm, Python and Rust tooling. Podman ran the existing private Compose graph and prebuilt integration image. The image mounts the backend source and tests read-only. These results remain earlier evidence, rather than newly executed backend or SDK qualification for the refactor.

| Check | Observed result |
| --- | --- |
| `pnpm check:backend` | Passed. Formatting, Ruff, strict Pyright, 1,625 host tests and 13 OpenAPI contract tests passed. The host run skipped 511 integration cases as designed. |
| `pnpm check` | Passed. Repository formatting, linting, typing, CLI/xtask tests, SDK-tool tests and backend tests passed. |
| `pnpm build` | Passed all four tasks. |
| `cargo test --locked -p inframeld-cli --lib discovery` | Passed all ten discovery tests. |
| Strict CLI/xtask Clippy and rustdoc | Passed. |
| Explicit OpenAPI and all three SDK regeneration | Passed. Generated sources were not edited by hand. |
| Complete unfiltered `pnpm sdk:verify` | Passed all stages for Rust, TypeScript and Python. Each of the five HTTP profiles passed 88 cases. Regeneration drift, native regressions, package archives and installed consumers passed. The evidence report records `partial: false`. |
| Pinned `cargo-deny` 0.20.2 dependency audit | Passed advisory, ban, license and source checks after applying the two developer-approved advisory exceptions documented below. Duplicate-version warnings remain permitted by the existing policy. |
| `INFRAMELD_CONTAINER_RUNTIME=podman INFRAMELD_INTEGRATION_IMAGE=localhost/inframeld-integration-tests:local pnpm test:integration` | Passed 511 tests with no skips in 248.30 seconds on the final backend revision. The wrapper exited zero. |
| Post-run Podman resource assertions | Passed. No project containers, networks or disposable TLS volumes remained. Both named database volumes existed. |

The generated OpenAPI SHA-256 for the complete SDK run is `c53819a5e28c83e5223f124ceb4fd60e245d59b9eaa36e23c35617d927fa350a`. Affected skill metadata and relative file links also passed validation. Skill activation rules did not change.

The backend emitted the existing Starlette/AnyIO deprecation warning. No test skip was added to bypass a discovery requirement.

The real-provider comparison uses private HTTP service addresses inside the isolated test graph. It qualifies projection/provider agreement, not manually registered HTTP or end-to-end production HTTPS. The Rust tests use ephemeral certificates and synthetic metadata to qualify the client transport policy. They do not sign in through Hydra or validate production tokens.

## Rust structure refactor on 2026-10-29

The pre-refactor baseline passed all 25 authored Rust tests. The refactor keeps the supported runtime and tooling interfaces and changes their private organization. Runtime parsing and dispatch now live in `app.rs`, with version execution in `commands/version.rs`. Discovery exposes its existing API through [`discovery/mod.rs`](../../../apps/cli/src/discovery/mod.rs), with separate operation, installation/profile, URL-policy, OIDC-transport and error components. Managed-local context fields remain private, without a public constructor or deserialization path. The transport scenarios retain their assertions, and pure URL tests live beside the policy.

The xtask has private argument and application modules. Packaging resolves its existing inputs through `PackagingContext` and extracts tool admission and embedded-metadata collection into focused helpers. Its [`verify` facade](../../../apps/cli/xtask/src/verify/mod.rs) preserves the existing evidence and exports over archive preflight and native qualification modules. Archive and process algorithms remain unchanged. Superseded source files were removed after moving their implementations.

Both authored manifests now deny `missing_docs`. The 20 baseline public-documentation gaps were resolved, with module overviews and documentation for meaningful internal components. Local and CI public rustdoc checks include all features. Private-item documentation remains available for inspection. The accepted command lifecycle diagram is unchanged, and general presentation, target persistence and login remain separate work. There is still no executable discovery command. The [manual inspection guide](../guides/server-discovery.md#manually-check-the-current-delivery) retains the actual command surface and its verification limits.

| Check personally run for the refactor | Observed result |
| --- | --- |
| Both authored crates' complete `cargo test --all-features` | All 25 existing tests passed, including all ten discovery scenarios. Three added documentation examples passed. Two execute locally and the discovery network example checks compilation only. |
| Optimized xtask `qualification` tests with all features | All five passed, including explicit failure gates, installation conflicts and unexpected user-state writes. |
| Selected-package rustfmt, strict all-target/all-feature Clippy and builds | Passed with denied warnings and missing public documentation. Both default and all-feature builds passed. |
| Strict public and private-item rustdoc with all features | Both passed. The private-item check caught an ambiguous function/module link, which was corrected and both views rerun. |
| Before/after command characterization | All 15 captured cases matched byte for byte for stdout, stderr and exit status. Cases include offline help/version, invalid invocation and xtask's actionable missing-tool failure. |
| Native reproducible packaging with checksum-verified cargo-dist 0.33.0 | Passed on `aarch64-apple-darwin`. Two builds of the refactored source produced identical archive and executable hashes and passed installation, permission and offline-execution qualification. |
| `pnpm check` | Passed. CLI lint, typing, docs and tests executed without Turbo caching. SDK-tool typing and tests also executed. Unchanged backend/web tasks and OpenAPI checks reused existing Turbo evidence. |
| `pnpm build` | Passed all four tasks. The CLI build executed, with the other three tasks served from the existing cache. |
| Documentation and scope checks | Both affected skill entry points passed metadata validation. Local file and anchor links passed validation, the lifecycle diagram was preserved and obsolete source links were removed. Hash comparison confirmed all 609 recorded lockfile, audit-policy, backend, OpenAPI and generated SDK files remained unchanged. |

Native evidence records source revision `8a19144977c9ec7c02fb6daf44f8c3a1a8eec5f1` with `sourceDirty: true`, development version `0.0.0` and no qualified runtime. The repeated archive SHA-256 is `1fa4f15c6b1fc54607d6c0206f65964781da53b1d54b3469e0ea157b96c5655f`. The repeated executable SHA-256 is `39cbe16ba2c36dd236679f44a59672243519f98276a4acd01e7601f48b0347e5`. These compare the two refactored builds in one local environment, not binaries from before and after the refactor or a released revision.

No dependency, public command, JSON contract, credential behavior or SDK generation was added in this refactor. Backend integration and full SDK regeneration/conformance were not rerun for this Rust-only change. Earlier evidence above remains explicitly separate. Docker CI and the remaining native targets still require final published-revision execution as described below.

## Discovery URL validation alignment on 2026-10-29

The subsequent review reproduced a configuration mismatch: Python accepted malformed host authorities that Rust rejected, and raw hostname comparison missed encoded, IDNA and IPv6 aliases of configured administration endpoints. New behavioral tests observed 20 intended failures before implementation. The existing Rust policy passed the matching characterization cases without production changes.

The backend now uses [`PydanticDiscoveryURLVerifier`](../../../apps/backend/src/inframeld_backend/access/infrastructure/verifiers/pydantic_discovery_url_verifier.py) in Access infrastructure. Its maintained `AnyHttpUrl` parser validates authorities and supplies normalized endpoint components. Raw syntax checks still reject parser repairs, and configured identity strings retain their exact spelling. The original 8,192-byte UTF-8 limit remains, including valid inputs longer than `HttpUrl`'s default limit. The admin guard compares scheme, host, effective port and path with its existing trailing-slash equivalence. Different paths, schemes and ports remain distinct, including explicit port zero. Managed-local syntax matches Rust's original literal `http://127.0.0.1` rule. Parser failures return controlled messages without retaining parser exceptions as causes or contexts.

The former domain validation module and its imports were removed. Pydantic remains outside domain code. No dependency, schema, generated SDK, persistence or Rust production behavior changed in this follow-up.

| Check personally run for URL alignment | Observed result |
| --- | --- |
| Focused Python discovery and SDK witness tests | Baseline: 47 passed. After adding regressions, discovery alone reported 20 behavioral failures and 48 passes. After implementation, all 90 focused cases passed. |
| `pnpm check:backend` | Passed formatting, Ruff and strict Pyright with zero typing diagnostics. All 1,668 host tests passed, with 511 integration cases skipped by the normal host-run policy. All 13 OpenAPI contract tests passed. |
| Both authored Rust crates with all features | All 27 tests and three doctests passed, including 12 discovery tests. The new URL cases cover malformed authorities, supported private/Unicode/encoded identities, byte-budget boundaries and managed-local aliases. |
| Strict authored Rust checks | Selected-package rustfmt, all-target/all-feature Clippy and all-feature public rustdoc passed with denied warnings. |
| `pnpm check` | Passed. Backend and CLI lint, typing and tests executed, along with fresh OpenAPI checks. Unchanged SDK-tool and web tasks reused their existing Turbo evidence. |
| Offline manual configuration recipe | Executed the exact [guide recipe](../guides/server-discovery.md#check-url-syntax-without-starting-services). It printed `valid: accepted unchanged=True` and `invalid: rejected`, with no services or saved state. |
| Scope and documentation checks | Repository comparison against the pre-fix snapshot confirmed changes were limited to the verifier move, its callers/tests and the approved documentation. Relative links, affected skill metadata, formatting and obsolete-identifier checks passed. |

The existing Starlette/AnyIO deprecation warning remains. Full provider integration, SDK regeneration/conformance and native packaging were not rerun for this configuration-only fix. Earlier results above remain earlier evidence. Final published-revision Docker, SDK and native CLI CI qualification remains pending below.

## Dependency audit assessment

`openidconnect` 4.0.1 is the latest published release observed during this check. Its RSA and elliptic-curve dependencies are mandatory even with default features disabled. The initial audit rejected `rsa` 0.9.10 under [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) and `crypto-bigint` 0.5.5 under [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html). RSA has no patched release. The big-integer fix requires 0.7.6 or newer, outside the selected elliptic-curve dependency constraint. A compatible lockfile update cannot resolve either finding.

Both advisories concern operations on cryptographic secrets. The inspected discovery path fetches and deserializes public metadata and public keys. It does not load private signing keys, decrypt messages, sign tokens or perform secret-integer arithmetic. The assessment is that these timing attacks are not reachable through this discovery behavior. This is a scoped code-use assessment, not a claim that the dependency versions are patched.

On 2026-10-28, the developer approved retaining `openidconnect` with two explicit advisory-ID exceptions. Both are recorded in `deny.toml` with the public-metadata-only rationale. Reassess their applicability when dependencies or cryptographic usage change, and before introducing private-key or secret-integer operations. Remove the exceptions when compatible patched dependencies become available. The affected versions remain unpatched. Other advisories, license checks and source restrictions retain their existing policy.

## Pending qualification

No commit, push, PR update or CI dispatch was performed for this implementation. Docker execution, applicable Linux/macOS SDK jobs, the evidence aggregate, Backend foundation, Quality and all four native CLI target checks remain pending on the final published revision. Local Podman and macOS checks do not establish those results. Issue closure should use the actual final-revision CI evidence and the shared Definition of Done.
