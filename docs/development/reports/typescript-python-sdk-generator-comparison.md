# TypeScript and Python SDK generator comparison

Subsequent maintenance: [ADR-0092](../../adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) replaces the tooling and adds regressions for field presence, constants, explicit null and stronger wire assertions. The measured results below remain historical evidence for their original cases, not exhaustive schema qualification.

> **Reproduction retired:** [ADR-0091](../../adr/ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) removes unselected implementations and the comparison commands. The measured results below are retained historical evidence. Former source locations and reproduction instructions are no longer available in the active tree. Use the [SDK tooling runbook](../../../packages/sdk-tools/README.md) for current verification. No historical Git revision is asserted for these originally uncommitted artifacts.

> **Subsequent selection:** [ADR-0089](../../adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) records the accepted TypeScript and Python generator choices. [ADR-0090](../../adr/ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) accepts shared three-SDK conformance, whose unified runner and CI gates await implementation. The dated study below retains its original recommendations, results and qualification limits.

Date: 2026-10-27. Status: qualification evidence and recommendations awaiting selection review. Rust's accepted decision remains [ADR-0088](../../adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md).

## Recommendation

For example, a caller creating a project grant must preserve `canGrant: false`, distinguish an omitted nullable request field from an explicit null and retain the received HTTP response when decoding fails. A generated type annotation alone cannot establish those properties.

Recommend **Hey API TypeScript with Fetch, generated Zod success-response validation and the raw-failure-body patch**, and **OpenAPI Generator Python with HTTPX, Pydantic 2 and the three resource fixes**. Both patched candidates pass the common 33 scenarios in both tested calling environments, plus their applicable static/model checks, regeneration checks and external consumption checks. No unpatched candidate passes all correctness gates. Publication, stable names and adoption are separate work.

The Python result is different from a recommendation based on concise signatures alone. openapi-python-client is attractive and its multipart/metadata gaps are patchable, but its scalar deserializers use unchecked casts. It accepts a boolean or array where the contract requires a string/integer union. Fixing that properly would require a broader validation change than the observed OpenAPI Generator resource fixes. Pydantic's runtime validation is a material advantage for this contract.

Modern technology is a preference after correctness. Here that means the native OpenAPI 3.1 contract, standard Fetch/HTTPX transports, ESM, abortable requests, generated runtime validation, ordinary installable packages and a small source patch surface. A newer version or a shared generator brand across languages is not evidence of correct wire behavior.

## Reproduce and inspect

Run the commands in the qualification runbook (retired source: `../../../packages/sdk-qualification/README.md`) from the repository root. The individual selectors are listed there. `pnpm sdk:languages:compare` collects every selected candidate before returning a failure status. A nonzero exit for the full experimental matrix is expected because upstream baselines fail. The two recommended candidates can be selected independently and must return zero.

The authoritative production input is `contracts/openapi/v1/inframeld-v1.json`, native OpenAPI **3.1.0**. Its SHA-256 is **`e8b3cb46d7de089319061f7920fec23df1a645401ce8021dfef921d3e174fed0`**. The second input is Rust's existing native FastAPI schema fixture. Neither input is downgraded or edited for a generator. The [structured results](typescript-python-sdk-generator-results.json) record the measured stages, case outcomes and failed observations. Full logs and observations are emitted under `packages/sdk-qualification/artifacts/` on each run.

| Tool or environment | Evaluated version |
| --- | --- |
| Hey API TypeScript | `@hey-api/openapi-ts` 0.99.0 |
| Orval | 8.44.0 |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 |
| OpenAPI Generator | 7.26.0 |
| openapi-python-client | 0.29.1 |
| Hey API Python | `@hey-api/openapi-python` 0.0.24 |
| TypeScript / Zod | 5.9.3 / 4.6.7 |
| HTTPX / Pydantic | 0.28.1 / 2.14.1 |
| Node / pnpm | 26.6.0 / 12.4.0 |
| Python / Java | 3.13.12 / Temurin 25.0.2 |
| Browser | Playwright 1.64.1, Chromium 156.0.8078.4 |
| Executed platform | macOS 26.3.1 (a), ARM64 |

Exact npm dependencies and integrity values are in the isolated npm lock (retired source: `../../../packages/sdk-qualification/tooling/package-lock.json`). Python versions and distribution hashes are in the Python tooling lock (retired source: `../../../packages/sdk-qualification/tooling/requirements.lock`). Generator archive identities and patch order are in the patch manifest (retired source: `../../../packages/sdk-qualification/patches/manifest.json`). These files are authoritative for reproduction. This table records this experiment rather than prescribing future upgrade versions.

Orval 8.44.0 was chosen within the repository's three-day npm release-age policy rather than selecting the just-published 8.45.0. openapi-typescript declares a TypeScript 5 peer requirement. Installation with TypeScript 7.0.2 failed that constraint, so the study uses 5.9.3 without forcing peer resolution. OpenAPI Generator's HTTPX2 flavor was inspected in an initial probe and exhibited the same principal schema failures. The final retained Python candidates use the established HTTPX library flavor. This report's scores and build measurements refer to that final configuration.

## Correctness results

Each calling environment runs the same 33 named scenarios. The baseline is Rust's original 30, strengthened with wrong response field types, a missing required response field and wrong scalar/union response values. Scores are per environment, not a claim that every case exercises a distinct product workflow.

| TypeScript candidate | Node | Chromium | Static contract checks | Correctness conclusion |
| --- | --- | --- | --- | --- |
| Hey API | 28/33 | 28/33 | Pass | Loses raw failure text |
| Orval Fetch + Zod | 19/33 | 18/33 | Pass | Parses errors as the success schema and loses failure metadata |
| OpenAPI Generator Fetch | 21/33 | 21/33 | Fail | Scalar union types are too broad, typed HTTP errors and response validation are incomplete |
| openapi-typescript + openapi-fetch | 28/33 | 28/33 | Pass | No generated runtime response validation and incomplete parse-failure inspectability |
| **Hey API patched** | **33/33** | **33/33** | **Pass** | **Qualifies the evaluated configuration** |

| Python candidate | Sync | Async | Additional model probes | Correctness conclusion |
| --- | --- | --- | --- | --- |
| openapi-python-client | 28/33 | 28/33 | 4/8 | Multipart, parse-failure metadata and unchecked scalar casts |
| OpenAPI Generator HTTPX | 26/33 | 26/33 | 5/8 | Boolean enum, omission and parse-failure metadata |
| Hey API | 5/33 | 1/33 | 5/8 | Missing operation parameters, untyped responses and no generated async API |
| openapi-python-client patched | 32/33 | 32/33 | 4/8 | Multipart and metadata fixed, unchecked casts remain |
| **OpenAPI Generator HTTPX patched** | **33/33** | **33/33** | **8/8** | **Qualifies the evaluated configuration** |

The single passing Hey API Python async case is a local model roundtrip. It provides no evidence of asynchronous HTTP support. Its five sync passes are limited transport/model observations, not a usable API client. Generated methods such as `assign_project_use_only_grant(self)` take no path, header or body arguments and retain literal path placeholders. Repairing them in a test driver would invalidate the comparison.

All ten candidates generate, compile their generated source and pass clean external package consumption. OpenAPI Generator TypeScript's source compiles, but the separate negative type examples fail because a scalar union becomes an empty interface that accepts values outside the schema. This is a contract type failure, not an emitted-source syntax failure. The comparison records generation, source compilation, static/model failures and HTTP behavior separately.

### What the scenarios establish

The backend serves the actual health, session, consent inspection/decision and project-grant production routers. Authentication and application collaborators are controlled test doubles. The same server also serves the native nullable/union/pagination/multipart fixtures and explicit fault injection. No database, real identity provider, provider credentials or paid endpoints are involved.

- Bearer and cookie alternatives work, cookie-only consent rejects bearer credentials, competing credentials are rejected and CSRF/Origin handling is exercised.
- Query encoding preserves `a+b&/`, path UUIDs, camel-case request/response fields, enum values, idempotency headers, explicit pagination and upload bytes/filenames reach the real adapters correctly.
- Omission versus explicit null is checked against the JSON received by the backend. It is not inferred by reserializing a decoded model with default null fields.
- Delivered Problem Details, validation paths, status codes, request IDs and authentication challenges are observable through each candidate's native API.
- Invalid JSON, wrong response shapes, missing required fields, unexpected status codes, timeouts and lost responses produce inspectable failures in the recommended configurations. A lost response must result in exactly one backend dispatch. A timeout requires a native timeout error or cause and evidence that the request reached the backend.
- Chromium uses actual cookie storage, preflight/CORS and browser-supplied Origin. It does not spoof forbidden Cookie or Origin request headers. A cross-origin manual redirect is opaque by browser design. That case accepts the native opaque redirect response and requires one backend dispatch, without inventing an unavailable 307 status.

The eight Python model probes independently challenge required nullable fields, omitted optional fields, explicit null, the false boolean constant, invalid true values, invalid boolean/array union members and wrong string field types. TypeScript compilation examples test required nullable fields, scalar unions, future Problem Details codes, mixed string/integer validation paths and `canGrant: false`.

The test drivers expose native observations. They do not reissue operations, repair serialization, rebuild missing response metadata or manually deserialize untyped errors into a generated typed error. The OpenAPI Generator TypeScript driver uses its documented raw response envelope before calling its generated value decoder. openapi-fetch uses its generic typed operation runtime, not handwritten HTTP methods. Python's deliberately invalid grant case uses Pydantic's `model_construct` to exercise the backend's 422 response despite local request validation. That sends the invalid value unchanged rather than repairing it.

### Why the baselines fail

Hey API TypeScript already preserves status and headers in its fields result and rejects bad success bodies with generated Zod validators. Its client reads response text, but discards that text when parsing/validation fails or when an unexpected error body is parsed. Keeping the original text closes the five observed failures without replacing its transport or operation generation.

Orval's configured Fetch runtime validation applies the success schema to Problem Details responses too. Valid 401/403/422/503 responses therefore throw Zod errors without the original HTTP context. Invalid JSON also throws before returning status/headers. Its browser redirect envelope loses the native response kind. These are reusable generator issues, but no Orval patch was implemented. A potential fix was not counted as a pass.

OpenAPI Generator TypeScript exposes raw `Response` objects on HTTP errors but does not return declared typed Problem Details through the evaluated operation API. Some response converters accept wrong types or missing required fields as success. Its string/integer union model is an empty interface. Adding ad hoc decoding or validation in a driver would hide these gaps.

openapi-typescript with openapi-fetch is a small, modern and useful types-plus-runtime combination. It does not generate runtime validators. It accepts wrongly shaped 200 bodies as typed successes, while JSON decoding failures lose their response envelope. Middleware and a separately generated validator layer could be investigated, but that integration was not implemented or reported as qualified.

openapi-python-client treats the native unencoded multipart file schema as text and loses response context if its generated parser throws. Those two capabilities were patched successfully. However, its generated `_parse_choice` uses `cast(int | str, data)` and ordinary string fields are copied without validation. The common wrong-scalar case and four extra model probes still fail after patching. The retained patch experiment therefore does not qualify it.

OpenAPI Generator Python validates fields with Pydantic, but renders the native boolean enum as string values, incorrectly rejects `canGrant: false`, and marks absent nullable fields as explicitly supplied nulls in `from_dict`. Successful-response decoding exceptions also lose HTTP context. Three narrowly scoped resource changes fix the observed gaps while retaining its existing typed models, HTTPX operations and serializers.

## Patch implementation and maintenance

| Candidate | Patched generator assets | Result |
| --- | --- | --- |
| Hey API TypeScript | Shipped Fetch client implementation and result type | Retain original JSON/error text on failure |
| openapi-python-client | Multipart parser source and built-in error/endpoint templates | Recognize direct native multipart files and preserve rejected response context |
| OpenAPI Generator Python | Built-in `python/model_generic.mustache` and `python/api_client.mustache` resources | Correct boolean enums, preserve field absence and wrap decode failures with status/headers/raw body |

The exact patches are linked from the manifest (retired source: `../../../packages/sdk-qualification/patches/manifest.json`). Every experiment verifies original archive bytes and ordered patch hashes, checks application against fresh source and generates into separate candidate directories. No generated SDK source is patched afterward. OpenAPI Generator uses a copied verified JAR with its two built-in resources updated. No Java class changes or replacement custom-template directory are needed. Ordinary SDK compilation never runs these steps.

The patches refer to reusable generator capabilities rather than Inframeld endpoint names. Baselines remain intact for comparison. A future generator upgrade must re-evaluate those capabilities and remove fixes that become obsolete. No upstream contribution is required, and no generator upgrade rehearsal was performed here.

The preferred TypeScript configuration uses Fetch's fields response style and `throwOnError: false`, with generated validation of success responses. Request validation is disabled so backend validation failures can be observed consistently, and native multipart file inputs remain usable. Runtime validation of arbitrary error-body shapes, data-only results and `throwOnError: true` are not qualified modes. Public documentation must not promise equivalent metadata preservation for those other modes without extending the checks.

The Python configuration uses Pydantic models and the HTTPX library with `supportHttpxSync: true`. Its synchronous methods bridge to the generated async implementation on a background event loop. They are not an independently generated synchronous transport. The harness closes that client's transport on the corresponding generated loop. Concurrency stress, alternate event loops and calling synchronous methods from async application code are outside this evidence.

Both configurations use caller-controlled base URLs, credentials, explicit timeouts and disabled redirect following. No automatic retries or generated request tracing are introduced. Orval requires a small caller-controlled base-URL module because its Fetch output uses a generated runtime URL expression. That is configuration glue, not a competing HTTP client.

## Maintenance and consumer experience

Hey API gives TypeScript callers operation functions with typed bodies, query/path parameters and a native response envelope. Its built-in Zod integration avoids designing a separate validation middleware layer. The selected patch touches two shipped client assets and retains the standard Fetch implementation. Its generator is in active initial development, so exact pins and qualification are important.

OpenAPI Generator Python is more verbose than openapi-python-client and has a Java generation dependency. Generated Python consumers need no Java or Node. Pydantic provides stronger runtime model checks, and native detailed results/exceptions expose the metadata required here. The resource patch is smaller in scope than adding a new scalar validation system to the attrs client. Generated sync bridge naming and lifecycle deserve clear public usage guidance before publication.

No candidate wins by package size alone. The recommended TypeScript artifact depends on Zod at runtime. The recommended Python artifact has the larger Pydantic dependency set. Those costs buy capabilities that affect correctness for the inspected contract. The structured results include each clean consumer's installed runtime package versions.

Each candidate has distinct experimental outer package metadata, license notices and publication protection. TypeScript packages are private. Python packages carry `Private :: Do Not Upload`. Generated inner packaging files remain comparison evidence, while the outer package configuration owns the artifacts evaluated here. Clean consumers install npm tarballs or Python wheels with only declared runtime dependencies. Python imports confirm that neither backend modules nor the Python generator are installed. NodeNext checks use the packaged declaration tree, not workspace source paths.

## Build cost

The structured results record clean and repeated builds separately from package installation. TypeScript's repeat uses incremental declaration state with a fresh bundle invocation. Python's repeat is a warm wheel build, not an incremental compilation claim. Temporary build output is removed before each clean TypeScript build. Source archives, generator installation and dependency downloads are not included in these build timings.

| Candidate | Clean build, ms | Repeat build, ms | Artifact, KiB | Installed runtime packages |
| --- | --: | --: | --: | --: |
| ts-hey-api | 499 | 265 | 35.0 | 2 |
| ts-orval | 345 | 261 | 23.1 | 2 |
| ts-openapi-generator | 350 | 232 | 28.9 | 1 |
| ts-openapi-fetch | 260 | 231 | 19.1 | 3 |
| py-openapi-python-client | 314 | 229 | 28.3 | 9 |
| py-openapi-generator | 244 | 234 | 47.3 | 15 |
| py-hey-api | 230 | 217 | 11.6 | 15 |
| ts-hey-api-patched | 413 | 285 | 35.0 | 2 |
| py-openapi-python-client-patched | 245 | 229 | 28.8 | 9 |
| py-openapi-generator-patched | 240 | 231 | 47.7 | 15 |

Build timings were collected with `node packages/sdk-qualification/run.mjs package` after explicitly clearing prior bundle/declaration output or setuptools build and egg metadata directories. Other stages come from the full comparison command. Runtime package counts include the experimental SDK itself.

These are one-run observations for a small delivered contract on this machine. They are not statistically significant performance rankings or a forecast of build cost for a large API. Tool setup was verified from the committed npm/Python locks using existing download caches. Initial browser downloads were separate, and no cold-download benchmark was conducted.

## Checks and limits

Personally executed:

- The full ten-candidate comparison, including native generation, fresh-directory drift checking, generated-source compilation, static/model probes, both calling environments and clean external consumers.
- Scaffold-first red/green tests for the shared behavioral oracle, omission/null witnesses, invalid-shape/scalar faults, browser origin handling, preservation of malformed incoming JSON validation and drift detection. The drift test detects changed, added and removed output in temporary trees.
- Seventeen shared oracle, drift, result-completeness and pinned-source preparation tests, including omitted/duplicate case rejection, modified archive/patch rejection and failed patch application.
- Backend contract suite, **22 passed**, native OpenAPI check, **13 passed**, and changed backend test-support Ruff and Pyright checks.
- The existing selected Rust SDK qualification, **30/30** scenarios and its existing synthetic patch capability suite. Rust source, selected strategy and historical comparison evidence are preserved.

The manual Linux/macOS CI matrix (retired source: `../../../.github/workflows/sdk-language-qualification.yml`) is added but has not been dispatched. Only local macOS ARM64, Node 26.6.0, Python 3.13.12 and the recorded Chromium runtime were executed. Other Python/Node versions, Linux, Firefox/WebKit, generator upgrade rehearsals and upstream test suites for the new generators remain unrun. SDK compilation and package consumption are separate from a complete application test run.

Durable jobs, receipts, stateful cross-SDK domain journeys, real Hydra/Kratos login and actual permission persistence remain unqualified where production HTTP workflows do not yet exist. The shared scenarios test SDK parity against the same backend process. They are not evidence of those future product workflows. SSE, streaming, binary response APIs and multipart variants beyond the delivered file fixture were not qualified for these new candidates. Rust's separate synthetic capability results are not inherited by TypeScript or Python. A newly delivered protocol must add its own common scenario before it is promised by a public SDK.

Server-version compatibility, registry publication, stable package names, browser login/credential storage, CLI implementation and a public HTTP escape hatch remain separate decisions. The recommended generators qualify the evaluated configurations and delivered contract, not every possible OpenAPI 3.1 feature or future API shape.

## Primary external documentation

These references describe available configuration and declared capabilities. Local generated source and executed tests determine the results above.

- [Hey API TypeScript](https://heyapi.dev/docs/openapi/typescript/get-started), [Fetch client](https://heyapi.dev/docs/openapi/typescript/clients/fetch), [Zod integration](https://heyapi.dev/docs/openapi/typescript/plugins/zod).
- [Orval output configuration](https://orval.dev/docs/reference/configuration/output/).
- [OpenAPI Generator TypeScript Fetch](https://openapi-generator.tech/docs/generators/typescript-fetch/) and [Python options](https://openapi-generator.tech/docs/generators/python/).
- [openapi-typescript](https://openapi-ts.dev/introduction) and [openapi-fetch](https://openapi-ts.dev/openapi-fetch/).
- [openapi-python-client](https://github.com/openapi-generators/openapi-python-client) and [Hey API Python](https://heyapi.dev/docs/openapi/python/get-started).
