# Maintain the generated Rust SDK

Alice adds a delivered operation and wants to call it from the CLI. Regeneration supplies its models and method when it uses qualified shapes. Wrong bytes need a retained regression and a reusable generator fix, without editing emitted Rust.

[ADR-0088](../../../../docs/adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) selects the generator. [ADR-0091](../../../../docs/adr/ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) promotes `inframeld-sdk` and retires baselines. [Shared maintenance](../../inframeld-sdks/references/generator-maintenance.md) owns provenance, source patches, upgrades and retirement. The [tooling runbook](../../../../packages/sdk-tools/README.md) owns commands and caches.

## Choose the affected work

Read generator versions, archive identity, patch order, digests and local revision from [the manifest](../../../../packages/sdk-tools/generators/manifest.json). The installed Rust toolchain follows [repository configuration](../../../../rust-toolchain.toml), while [Rust generator options](../../../../packages/sdk-tools/generators/rust.toml) own the selected mode. Do not maintain another pin or fixed patch-count table here.

For an endpoint use [Extend qualification](#extend-qualification), for a defect use [Fix a generator defect](#fix-a-generator-defect), and for a changed source use [Upgrade or retire a patch](#upgrade-or-retire-a-patch). [Diagnose the failing stage](#diagnose-the-failing-stage) separates failures.

## Extend qualification

Use the promoted crate and ordinary shared feature tests. The [native driver](../../../../packages/sdk-tools/drivers/rust/src/main.rs) supplies native bindings and protocol observations to shared TypeScript assertions. It does not repair requests, replace union/error models, invent headers or repeat work. Real routers use controlled collaborators without provider credentials or paid endpoints.

Retain Rust's native model checks and [synthetic capability tests](../../../../packages/sdk-tools/fixtures/rust-capabilities/tests/wire.rs). Binary, live-stream, parsed SSE and builder evidence belongs to those synthetic Rust capabilities. It does not establish missing product jobs, receipts, application-specific streaming helpers or another language's support.

## Fix a generator defect

Follow shared regression-first source maintenance, including relevant negative cases and license notices. Upstream contributions are not required. Preserve native schemas and avoid handwritten HTTP, overlays and post-generation rewriting. Review generated signatures, models, serializers and dependency declarations together.

Default construction honors the configured timeout, currently five seconds, and disables redirects/retries. Keep caller-provided reqwest transports unchanged through `with_client`. Deliberate overrides change the qualified default policy. Keep credentials and selected tracing behavior. Main JSON methods expose generated response enums for multiple status/media bodies, including mixed bodyless unit variants and class/default selection. Select exact status before class/default and exact media type before wildcards. A missing content type needs an unambiguous representation. Primary and secondary response roots preserve native nullability. Buffered JSON decoding rejects invalid UTF-8 instead of parsing lossy diagnostics. The driver exposes `ApiError.raw_body` with UTF-8/base64 encoding while retaining text in diagnostics. Native regressions cover cancellation of an active operation and reuse of its client. Successful operations and builders return `ApiResponse<T>` with typed body, numeric status and original headers. For metadata changes qualify affected JSON, text, empty, buffered binary, live-byte and parsed SSE paths, repeated headers and malformed bodies. Body mapping retains metadata and obtaining live metadata cannot wait for the entire stream.

Compile production and fixture clients, run shared scenarios and relevant capabilities, check clean regeneration including dependencies, run available generator library tests and consume a crate archive externally. Source-archive library tests do not establish the upstream integration suite. Keep installation/download/generation costs separate from SDK compilation.

Retain generated source and Cargo dependencies/locks through explicit generation. Ordinary compilation requires no Python, generator or backend. Do not format or hand-edit emitted Rust. Format handwritten drivers/tests directly, then regenerate any accidentally touched output.

## Upgrade or retire a patch

Follow shared upgrade policy. A patch that stops applying is not thereby obsolete. Its original regression must pass without the local fix before retirement, and the regression stays afterward.

Preserve the metadata API and its opt-out body-only compatibility. Verification generates a temporary metadata-disabled client and compiles its consumer contract. The retired comparison's byte-identical baseline-production observation remains historical evidence, not the current test's claim.

Adoption of a Rust generator upgrade requires Linux/macOS qualification. The workflow now implements that matrix, but keep adoption pending if its applicable run is unexecuted or failed. Do not dispatch CI merely to answer a question. Reports' unrun remote-platform and upgrade-rehearsal limits remain historical facts.

## Diagnose the failing stage

Use the [shared failure table](../../inframeld-sdks/references/generator-maintenance.md#diagnose-the-failing-stage) for checksum, patch application, compilation, wire, drift and external-consumer failures. Rust boolean constants use generated constant types. Required nullable fields retain the presence requirement, and optional non-nullable fields reject a supplied null. Inspect the [runner](../../../../packages/sdk-tools/src/cli.ts), [generator preparation](../../../../packages/sdk-tools/src/workflows/generate.ts) and [source utility](../../../../packages/sdk-tools/src/generation/patched-source.ts) for mechanics.

Source verification precedes that SDK's generation. Successful other SDKs or later failures can leave changed output. Inspect the tree and preserve unrelated work. Never drop failing results. A second serializer, broad analyzer/runtime redesign, recurring endpoint-specific exceptions or obstructive upgrade conflicts trigger reconsideration under shared policy. No fixed patch count or assumed HTTP escape hatch replaces that review.

## Authority and evidence

The [Rust report](../../../../docs/development/reports/rust-sdk-generator-comparison.md) retains dated findings, while its unselected implementations and reproduction tooling are retired. Local Cargo path dependencies need no registry publication. Keep version 0.0.0 and `publish = false` until separate release work changes them.

Application Contracts retains [HTTP meaning and server-version compatibility](../../inframeld-application-contracts/references/decision-cli-server-compatibility.md). Follow the accepted matching-release policy in ADR-0095. Remote enforcement and release-pair qualification remain separate work. Promotion changes neither the generator choice nor historical qualification results.

Read the [hardening report](../../../../docs/development/reports/sdk-hardening-verification.md) for current native consumer, typing and preparation evidence. Production generator pins remain authoritative in configuration, and no newer-release upgrade is implied by clean preparation of the current source.

[ADR-0094](../../../../docs/adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) and its [verification evidence](../../../../docs/development/reports/sdk-response-fixes-verification.md) record subsequent response-selection/default-constructor fixes without rewriting historical results.
