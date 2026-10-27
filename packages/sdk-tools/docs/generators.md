# Fix and upgrade SDK generators

Alice discovers that an optional non-nullable property accepts explicit null. She first adds a negative native model test and a malformed-response case. After observing the intended failure, she fixes the shared generator mapping and regenerates. Editing the emitted model would lose the fix on the next generation.

## Find the responsible input

The [manifest](../generators/manifest.json) owns original archive identities, ordered patches and digests. The concrete [Rust](../src/generation/rust.ts), [TypeScript](../src/generation/typescript.ts) and [Python](../src/generation/python.ts) modules own preparation and emission. [Shared source preparation](../src/generation/source.ts) verifies inputs before use. Read those authorities instead of copying versions into documentation.

Rust compiles verified patched source outside the application workspace. TypeScript privately stages verified copies of the generator and its already-locked shared parser, using each package's own dependency closure. Patches preserve parser response information, generate operation-owned validators and update shipped Fetch assets. Installed workspace dependencies are never patched. Python updates built-in JAR resources before generation, retaining Java as a development dependency only. Its native [selective-generation options](https://openapi-generator.tech/docs/customization/#selective-generation) retain models, operations and runtime support, including the typing marker, and omit unused repository/CI scaffolding.

## Retain a regression and patch the source

Inspect the native schema and generated signature. Add the smallest meaningful failing test. Use a native model check for representation behavior and a shared HTTP case when decoding or wire behavior is affected. Follow scaffold-first TDD for new harness behavior.

Change verified generator source or resources in a temporary working directory. Produce a targeted source diff, append it in manifest order and record its digest. Existing source and patch digests must match before applying anything. A checksum failure requires investigating provenance and changed bytes, not blindly updating a hash.

Run explicit generation, inspect the output and run full verification. Rust dependency changes update the owned dependency table through a TOML parser while retaining other manifest sections. Check clean regeneration and deliberate drift, native models, HTTP behavior, available generator regressions and archives consumed outside the repository.

## Upgrade or retire a patch

An upgrade is deliberate work, not routine dependency churn. Verify the proposed archive, rebase the retained patches and inspect generated API/dependency changes. A patch that no longer applies is not automatically obsolete. Its original regression must pass without it before removal, and the regression stays afterward.

The current [shared policy](../../../.agents/skills/inframeld-sdks/references/generator-maintenance.md) owns complete maintenance obligations and reconsideration triggers. A broad analyzer/runtime redesign or recurring endpoint-specific exceptions need an architectural review. Upstream contributions are not required.

## Diagnose the stage

An existing bad cached archive survives retries because preparation downloads only when the archive is absent. Locate the effective cache through [configuration](../src/config.ts), preserve the suspect bytes and investigate their origin first. After establishing corruption and verifying the intended source, replace only that archive with verified bytes and rerun setup. Do not delete the whole cache or change a digest simply to bypass the failure.

Rust and TypeScript archive preparation clean failed temporary patch trees. Preserve an independent temporary copy of the verified archive when investigating a conflict. Extract it and enter the manifest's `archiveRoot`, initialize an isolated Git repository, apply earlier ordered patches and run `git apply --check --whitespace=error-all` on the conflicting patch.

Python uses a verified JAR and an explicit resource list rather than a tar archive root. Mirror [its adapter](../src/generation/python.ts) in an independent `/private/tmp` directory: copy the verified JAR, extract exactly `patchedResources` with `unzip`, initialize Git in that resource directory, verify patch digests and check/apply earlier ordered patches. Check the conflicting patch without updating the copied JAR or generating SDK output. Do not invent an `archiveRoot` for Python. Its failed resource tree remains in the selected cache until the next preparation replaces that destination. Copy it to a separate temporary directory before retrying if it is needed for diagnosis.

The setup failure retains Git's diagnostic output. The [shared preparation implementation](../src/generation/patched-source.ts) and concrete language adapter own the exact commands. Do not debug by editing emitted SDK source or treating a modified cache as authoritative.

Keep archive verification, patch application, compilation, behavior, drift and packaging failures separate. `sdk:check` compares temporary output and leaves committed source untouched on failure. `sdk:generate` stages output before replacement, but a later filesystem failure can still leave a partial working-tree update. Inspect and preserve unrelated work.

Applicable Linux/macOS qualification is required for adopting generator changes. The workflow's existence does not prove those platforms executed. Do not dispatch CI merely to explain a failure. Public release and server compatibility remain separate work.

## Patch purposes and retirement

Read exact versions, digests and order from the [manifest](../generators/manifest.json). This table identifies why each retained patch exists, the regression that protects it and the evidence needed before retiring it. A patch failing to apply is a conflict to investigate, not evidence that its fix is upstream.

| Manifest patch | Purpose and protected behavior | Retirement evidence |
| --- | --- | --- |
| Rust `0001-native-multipart-files` | Native file bytes, names and MIME arguments. Shared upload and synthetic multipart cases. | Unpatched proposed source passes exact-byte/name upload cases and native capability checks. |
| Rust `0002-success-response-metadata` | Status/headers across buffered, empty and streaming results, with the metadata opt-out. Shared metadata, synthetic streaming/SSE/builder cases and body-only consumer. | Proposed source preserves the same public metadata and opt-out signatures across those regressions. |
| Rust `0003-preserve-presence-and-boolean-constants` | Required-nullable presence, non-nullable rejection and boolean constants. Native models and malformed shared responses. | All presence/null/constant regressions pass without the patch. |
| Rust `0004-nullable-response-roots` | Nullable response roots and strict byte-based JSON decoding. Nullable alternative and invalid-UTF-8 shared cases. | Legitimate null and malformed UTF-8 cases both pass without the patch. |
| TypeScript `0001-qualified-capabilities` | Native raw failure text and inspectable response context. Malformed/error-response cases. | Native fields results retain the same available context and raw text without the patch. |
| TypeScript `0002-response-integrity` | Generated status/representation/body metadata, operation-owned validators, required JSON validation and strict UTF-8 decoding. Native response tests plus shared nullable/bodyless, invalid-status/body/MIME/UTF-8 cases. | All selected-mode regressions pass with upstream operation metadata and runtime behavior, without local compensation. |
| Rust `0005-default-transport-policy` | Default timeout, no redirects/retries and preserved caller transports. Native constructor/deadline/redirect tests. | The same default-constructor and explicit-override behavior passes unpatched. |
| Rust `0006-json-response-selection` and `0007-mixed-and-default-json-responses` / `0008-json-error-representations` | Status/media-specific typed variants, including secondary nullability, mixed bodyless/default responses and alternate typed error media. Exact bodyless errors precede class/default schemas. Shared response variants and malformed alternatives. | Every status/media/null/body-absence regression passes with accurate native types unpatched. |
| TypeScript `0003-typed-failures-and-response-validators` | Honest failure union and validated API errors. Static narrowing and native failure tests. | Unpatched output preserves the same typed classification and HTTP context. |
| TypeScript `0004-default-transport-policy` | `timeoutMs`, combined cancellation and manual redirects. Native default/override/invalid-config tests. | The same transport defaults and configuration validation pass unpatched. |
| TypeScript `0005-response-representations` and shared-parser `0001-shared-response-representations` / `0002-shared-default-response-types` | Preserve every declared JSON representation through parsing, types, metadata and validators. Shared status/media cases and strict signature checks. | Both parser information and emitted behavior pass all alternatives without either patch. |
| TypeScript `0006-preserve-classified-failure-evidence` | Deadline ownership, body-collection timeout classification and original structured failure retention when hooks throw. Native failure tests. | Those failures preserve their classification/evidence unpatched. |
| Python `0001-qualified-capabilities` | Native boolean constants and inspectable decoding failures. Model/HTTP malformed-response cases. | Native models and errors pass those regressions unpatched. |
| Python `0002-preserve-field-presence` | Missing versus null, including supplied defaults. Native model and independent wire witnesses. | All presence/default/null cases pass unpatched. |
| Python `0003-response-integrity` | Nullable/bodyless/undeclared responses, strict primitive JSON decoding, native repeated headers/exact error bytes and accurate used signatures. Shared response/header/UTF-8 cases, native typing and installed consumers. | Both behavioral regressions and strict actual-call checking pass unpatched. |
| Python `0004-default-buffered-deadline` | Five-second default and scalar total buffered deadlines, tuple phase overrides, reuse/closure. Native sync/async lifecycle tests. | All default, override and lifecycle cases pass unpatched. |
| Python `0005-response-representations` and `0006-strict-container-and-default-responses` | Status/media maps, accurate union signatures, default selectors and strict JSON/container decoding before model conversion. Shared variants, malformed problems and native container tests. | All alternatives, native signatures and malformed-container regressions pass unpatched. |

The [response-fix report](../../../docs/development/reports/sdk-response-fixes-verification.md) supplements earlier evidence. The [hardening report](../../../docs/development/reports/sdk-hardening-verification.md) records the latest upstream lookup and preparation evidence. If no newer stable release exists, repeatable current-source preparation is useful evidence, but an upgrade rehearsal remains pending. Production pins must remain unchanged during isolated rehearsals.
