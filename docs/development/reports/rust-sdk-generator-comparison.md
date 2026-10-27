# Rust SDK generator comparison for issue #80

Subsequent maintenance: [ADR-0092](../../adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) replaces the tooling and adds regressions for field presence, constants, explicit null and stronger wire assertions. The measured results below remain historical evidence for their original cases, not exhaustive schema qualification.

> **Reproduction retired:** [ADR-0091](../../adr/ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) removes unselected implementations and the comparison commands. The measured results below are retained historical evidence. Former source locations and reproduction instructions are no longer available in the active tree. Use the [SDK tooling runbook](../../../packages/sdk-tools/README.md) for current verification. No historical Git revision is asserted for these originally uncommitted artifacts.

> **Subsequent selection:** On 2026-10-27, [ADR-0088](../../adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) recorded the selected Rust generator-and-patching approach. The observations and qualification limits below remain the evidence available before that selection, rather than a claim of SDK publication or new verification. Subsequent [ADR-0089](../../adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) selects TypeScript/Python configurations, and [ADR-0090](../../adr/ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) accepts a shared conformance target awaiting implementation. The historical future-language and adoption statements below describe the study at the time.

Observed locally on 2026-10-27. This report evaluates two unmodified generators and an isolated patched Rust candidate. It does not select a production SDK, authorize publication or close the remaining qualification work in #80.

## Recommendation

Prefer the isolated `openapi-to-rust-patched` candidate for the next Rust SDK iteration. Its two source patches resolve the measured upload and success-metadata gaps. It passes all 30 shared scenarios, 14 additional synthetic wire tests and the published generator library's 115 tests. Clean regeneration, metadata opt-out compatibility, local packaging and an external consumer build pass. Production adoption remains for developer review.

The unchanged baselines remain reproducible. `openapi-to-rust` 0.23.0 passed 28 of the 30 shared scenarios and OpenAPI Generator 7.26.0 passed 21. Neither unmodified candidate qualifies unconditionally. The patched result does not qualify future contracts, all schema forms or independent CLI/server releases. No backend schema weakening or handwritten application HTTP replacement was introduced.

The scenario count is supporting evidence, not a weighted score. Several failures share one cause. Correctness takes precedence over generated-code size and build time.

## Reproduce and identify the inputs

The [workspace guide](../../../packages/sdk-rust/README.md) describes prerequisites, package layout and all commands. From the repository root, with backend test configuration present and dependencies fetched:

```sh
pnpm sdk:generate
pnpm sdk:check
pnpm sdk:test
pnpm sdk:compare
```

Append `openapi-to-rust`, `openapi-to-rust-patched` or `openapi-generator` to evaluate one candidate. The test and comparison commands intentionally return nonzero for the recorded generator gaps. Logs and detailed machine observations go into ignored `packages/sdk-rust/artifacts/`. All selected candidates are evaluated before the command returns. The [recorded result summary](rust-sdk-generator-results.json) preserves the counts, individual scenario outcomes, pins and build observations without ephemeral server addresses or personal filesystem paths.

| Input | Observed value |
| --- | --- |
| Production contract | `contracts/openapi/v1/inframeld-v1.json`, unchanged native OpenAPI 3.1.0 |
| Production SHA-256 | `e8b3cb46d7de089319061f7920fec23df1a645401ce8021dfef921d3e174fed0` |
| Rust-native generator | Published `openapi-to-rust` 0.23.0, installed with its lockfile |
| OpenAPI Generator | 7.26.0, `rust` / `reqwest`, asynchronous, multiple-success-response mode enabled |
| Tool configuration | Version/checksum pins and generator options in `packages/sdk-rust/config/` |
| Local environment | macOS 26.3.1 (a), ARM64, Rust 1.95.0, Node 26.6.0, Temurin Java 25.0.2+10 |

The second schema is exported from the existing FastAPI payload, upload and pagination fixtures. It is test-only and is not merged into the public contract. The HTTP qualification process registers actual production health, session, consent and grant routers alongside those fixtures. Authentication and application collaborators are controlled test doubles. No database, Kratos, Hydra or model endpoint is contacted.

## Observed behavior

| Area | openapi-to-rust 0.23.0 | OpenAPI Generator 7.26.0 |
| --- | --- | --- |
| Production and fixture compilation | Pass | Pass |
| Delivered health, session, consent and grant operations | Pass | Pass |
| Bearer setters, injected cookies, CSRF/Origin, competing credentials and typed basic denials | Pass | Pass |
| Required null, optional absence/null and scalar-union payloads | Pass | Scalar `anyOf` becomes an empty `Choice` struct. Its `{}` request value is rejected by FastAPI, preventing the four combined payload scenarios from completing |
| Problem Details with string/integer validation paths and a future extension/code | Pass | `ValidationIssue.path` items become an empty `PathInner` struct. Deserializing the declared string/integer values fails |
| Explicit/default pagination and cursor transmission | Pass | Pass |
| Native FastAPI multipart upload, bytes and filename | Fail | Pass |
| Malformed successful response | Returns an API failure retaining status 200 and raw `{` body | Returns `Ok(ResponseContent { entity: None, ... })` in the tested mode |
| Unexpected 418 response | Inspectable failure with raw body | Inspectable failure with raw body |
| Redirect with following disabled | Returns an API failure for 307 | Returns `Ok` for 307 in the tested mode |
| Timeout and lost acknowledgment on a POST | Failure, with one observed request | Failure, with one observed request |
| Error headers and request-ID correlation | Preserved | Generated `ResponseContent` has no header field |
| Success response headers | Not exposed by the generated typed methods | Not exposed by generated `ResponseContent` |
| Regeneration and independent package consumption | Pass | Pass |

The native upload schema uses `contentMediaType: application/octet-stream`. `openapi-to-rust` emits `BodyContractFixtureUpload.file: String` and sends `form.text("file", ...)`. FastAPI rejects that field as an upload. The driver does not convert the generated operation into a hand-written multipart request. OpenAPI Generator emits an asynchronous file parameter and transmits the exact binary marker and filename successfully.

For unions, the problematic OpenAPI Generator models are inspectable in the committed generated files. The two unmodified baselines use no source patches, schema downgrades, overlays, custom templates or handwritten replacement union types. The malformed-success and redirect observations apply specifically to the selected `supportMultipleResponses=true` configuration. They are not claims about every OpenAPI Generator transport or option combination.

Validation paths can legitimately be sanitized to empty arrays by the backend. The real 422 test accepts that policy. A separate generated-model round trip tests nonempty string/integer paths against the declared schema. Likewise, the pagination case uses the existing base64url-compatible cursor syntax. The harness does not reinterpret server policy to favor a generator.

## Patched follow-up

The patch guide (retired source: `../../../packages/sdk-rust/patches/README.md`) owns the reproduction and upgrade procedure. Its manifest (retired source: `../../../packages/sdk-rust/patches/manifest.json`) pins the published 0.23.0 source archive, SHA-256, patch order and individual patch hashes. The [structured follow-up results](rust-sdk-patched-results.json) retain the input hashes, individual shared outcomes, test counts and build observations. The original [baseline results](rust-sdk-generator-results.json) are preserved separately.

| Source change | Implemented behavior |
| --- | --- |
| Multipart classifier | Native unencoded octet-stream string fields inside multipart requests use `MultipartFile`, including the existing nullable/reference/array paths. Encoded and JSON media strings remain text. |
| Success response emission and configuration | Opt-in `http_client.response_metadata = true` returns `response::ApiResponse<T>` with body, status and the response's original header map. Operation builders preserve the same envelope. |

The reviewable source diffs change five upstream Rust files with 91 inserted lines and 16 deleted lines. The upload diff touches one classifier. The metadata diff covers configuration plumbing, the envelope and shared return paths rather than individual endpoint implementations. It is larger because binary and streaming responses take different paths from JSON. This is evidence about the current patch size, not an estimate of future upgrade costs.

Generation downloads and verifies the original source, applies the ordered patches in an isolated temporary Git repository and builds outside the application Cargo workspace with the upstream lockfile. A manifest-derived cache key separates the patched executable from the original. Both archive and patch bytes are rechecked even when the executable is cached. No generated Rust is edited after generation. A cold default-cache installation and generation were personally exercised.

The patched production and FastAPI fixture crates use the original native inputs. A third crate uses a clearly synthetic capability schema. Its fourteen wire tests exercise typed JSON, text, 204, exact binary bytes, live raw/parsed events, binary streams, malformed/unexpected responses, repeated headers, query encoding and operation builders. Multipart coverage includes required, optional, referenced array files and text fields. The tests observe metadata before releasing streaming bodies, detecting accidental buffering.

The baseline was rerun before changes and reproduced its two failures. Seven Node runner tests pass, including identical preparation, corrupted archive/patch rejection, nonapplicable patch rejection and Git isolation inside a repository cache. Fresh generation with metadata disabled matches the baseline production tree byte for byte. The patched generator's available 115 library tests pass. The published archive does not contain its full upstream repository integration suite.

Personally run for this follow-up: `sdk:generate`, `sdk:check`, `sdk:test` and `sdk:compare` for the patched candidate, local package/external-consumer verification, patched-driver Clippy, seven runner tests and the seventeen affected backend contract/fixture tests. The backend tests retain one existing Starlette/AnyIO deprecation warning. `pnpm openapi:check` passed through its Turbo cache, and direct execution of its thirteen contract tests was included in the seventeen fresh tests.

The patched production output contains three Rust files and 56,832 bytes, with 101 runtime dependency entries under the same counting method as the baseline. A single follow-up clean check took 19.422 seconds and an unchanged check took 0.163 seconds. Installation, generator-source tests and downloads are excluded. These observations do not establish a performance difference from the earlier baseline run.

The manually dispatched Linux/macOS matrix now includes the patched candidate. It has not been dispatched. All follow-up evidence remains local macOS ARM64. Configured application-specific streaming helpers, multiple-success-body contracts, durable jobs, receipts, an HTTP escape hatch, publication and CLI/server compatibility remain outside this patch qualification. No production generator adoption is recorded by this follow-up.

## Maintenance, packaging and build cost

All SDK candidates have handwritten package manifests owning metadata and `publish = false`. Dependencies come from the generator's emitted declarations. The OpenAPI Generator wrapper enables Rustls and retains the untouched upstream manifest as `generated/Cargo.generated.toml`. This avoids Cargo excluding source inside an unintended nested package. These are packaging choices, not fixes to generated Rust behavior.

The pinned Rust generator installation succeeded with an upstream lockfile warning about yanked `chacha20` 0.10.1. This is observed generator-tooling evidence, not a vulnerability finding or a statement about the SDK runtime dependency graph.

Both production crates passed local `cargo package` verification and compilation by a clean external consumer using the extracted archive. Their generated code has no Python, Java, backend or CLI runtime dependency. Generators are required only for explicit regeneration. The `openapi-to-rust` notice preserves the upstream MIT notice for runtime portions. Candidate packages carry the repository's Apache-2.0 metadata.

| Single local observation          | openapi-to-rust | OpenAPI Generator |
| --------------------------------- | --------------- | ----------------- |
| Generated production Rust files   | 3               | 17                |
| Generated production Rust bytes   | 55,110          | 33,763            |
| Runtime dependency entries        | 101             | 106               |
| Fresh-target `cargo check`        | 14.535 s        | 11.221 s          |
| Immediate unchanged `cargo check` | 0.143 s         | 0.152 s           |

Each timing used a separate temporary target directory, the same Rust toolchain and the committed workspace lockfile. Dependency downloads and generator installation were excluded. These are single observations, not medians or a performance guarantee. Dependency entries are distinct `cargo tree --edges normal` lines, including version/feature graph repetitions where Cargo renders different entries. Build-time measurements concern the SDK libraries, not an installed CLI executable or product request latency.

`openapi-to-rust` offers convenient direct methods and explicit typed error variants. Consumers must use the contract-generated `types::ProblemDetails` carried by per-operation errors. Its separate generated `openapi_to_rust_problem` convenience profile is not Inframeld's full problem model and must not replace it. OpenAPI Generator exposes the response status and raw text, but missing headers and empty union models require more substantial changes than the two observed Rust-native gaps.

## Verification and remaining work

Personally run locally:

- Both pinned generators on unchanged production and native fixture schemas, followed by fresh-directory drift checks. Both passed.
- Four SDK crate compilations, two local package verifications and two independent consumer builds. Passed.
- Thirty identical qualification scenarios per candidate. `openapi-to-rust`: 28 passed, 2 failed. OpenAPI Generator: 21 passed, 9 failed.
- The backend fast suite: 1,538 passed, 505 service-dependent tests skipped, with one existing Starlette/AnyIO deprecation warning.
- `pnpm check`, including repository formatting, lint, strict typing, tests and OpenAPI drift. Passed.
- Focused Rust formatting and Clippy checks for both qualification drivers. Passed.
- Two Node behavioral tests for continuing after candidate failure and detecting changed/unexpected generated files. Passed.
- The Rust-native driver's two focused checks passed. The OpenAPI Generator union check remains an expected qualification failure, rather than being ignored or rewritten.

The manually dispatched workflow defines Linux and macOS jobs for each candidate, retaining logs and result JSON even on failure. That remote matrix has not been run. This local ARM64 result does not qualify Linux or other architectures. PostgreSQL/Kratos/Hydra integration tests were not rerun because this comparison deliberately uses controlled doubles.

Durable-job, receipt and additional response-variant qualification remain pending until their owning HTTP contracts exist. Complete CLI OAuth interaction, secure credential storage, public SDK releases and supported server-version ranges remain separate work. TypeScript and Python are confirmed future SDK targets and may select different generators against the same backend contract and scenarios. C# and Java SDK delivery remain tentative.

The patched follow-up resolves the two measured baseline gaps. Preserve its qualification as the API grows and review adoption separately. Do not treat this recommendation as adoption or as approval of PD-CONTRACTS-03.
