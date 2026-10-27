# SDK hardening verification

> Subsequent work: [response fixes and follow-up review](sdk-response-fixes-verification.md) address newly demonstrated public failure typing, response-variant and default-transport defects. Results below remain dated evidence for the earlier implementation. **Date:** 2026-10-27. This report records repository-local implementation and evidence for [ADR-0093](../../adr/ADR-0093-preserve-response-integrity-and-type-native-sdk-boundaries.md). It supplements the [earlier rebuild evidence](sdk-tooling-rebuild-verification.md) without rewriting historical results. No historical Git revision is claimed for uncommitted artifacts.

## Implementation and inputs

The selected generators, package identities, version `0.0.0` and publication protection remain unchanged. Verified source/resource patches now preserve response status/body/nullability, strict primitive and UTF-8 JSON decoding, repeated Python headers and exact available error bytes. Private protocol observations distinguish generated model decoding, generated schema validation, parsed JSON and no validation. Drivers retain body absence versus explicit null and expose driver defects separately from expected SDK failures.

The manifest and configuration remain authoritative for versions, hashes, order and options. The [patch maintenance table](../../../packages/sdk-tools/docs/generators.md#patch-purposes-and-retirement) identifies each purpose, regression and retirement condition. The snapshot at the start of this task covered 1,153 owned files and existing qualification evidence in a temporary directory. Historical comparison reports/results and production OpenAPI are preserved.

Handwritten Python drivers, tests and consumers use strict Pyright/Ruff in isolated tooling. Direct native bindings replace reflective method-name dispatch. Shared TypeScript checking is independent of the native TypeScript project, which runs after declaration building. Archive construction is separate from conformance execution. Installed consumers make real requests and inspect results/errors. Python exercises actual used pools on its sync bridge and async lifecycle.

Case registration/scoped retrieval/deletion bounds evidence state. Independent total dispatch counts survive deletion. Startup, cancellation, subprocess groups, browser processes and cleanup remain explicit owners with bounded deadlines/output. A failed close and its original execution failure remain visible.

## Checks actually completed

The final unfiltered `CARGO_NET_OFFLINE=true pnpm sdk:verify` passed for all three languages on macOS. The ignored `packages/sdk-tools/artifacts/summary.json` has schema version 3, `partial: false`, all common stages passed and every required language stage passed. Profile reports use version 2. The native contract SHA-256 is `e8b3cb46d7de089319061f7920fec23df1a645401ce8021dfef921d3e174fed0`.

| Check | Observed result |
| --- | --- |
| Shared feature tests | 54 cases in each of Rust, TypeScript Node/Chromium and Python sync/async, 270 passing case executions with no skipped or missing results |
| Handwritten tooling | Strict shared/native TypeScript checks, strict Python Pyright with zero errors/warnings, Ruff lint/format and compiled Rust bindings/consumer passed |
| Harness regressions | 45 Node tests passed, including protocol/result inventories, source verification, coverage, deadlines and cleanup |
| Native checks | Rust 6 model tests and 1 lifecycle test, TypeScript 8 response tests and 7 driver/resource tests, Python 16 model tests and 6 driver/lifecycle tests passed |
| Rust capabilities | 14 synthetic capability tests, 115 generator library tests and metadata-disabled external build passed, separate from HTTP counts |
| Backend fixture/OpenAPI | 30 contract tests passed, including 17 witness/control tests and 13 OpenAPI tests |
| Backend checks | `pnpm check:backend` passed, including strict checking/lint, 1,551 tests passed and 505 integration tests skipped, followed by 13 OpenAPI tests |
| Regeneration | Explicit generation and repeated clean temporary regeneration passed for every selected SDK, including ordered patch verification and dependency drift checks |
| Distribution | Crate, npm tarball and Python wheel built, then clean installed consumers made real success/error/recovery requests with typed results and metadata |
| Documentation/style | Repository `pnpm format:check` passed, including backend formatting, all 9 handwritten Rust files passed rustfmt, 585 local links/anchors across 22 changed Markdown files passed, all five affected skills passed `quick_validate.py` |

The backend emitted one Starlette/AnyIO deprecation warning. Skipped integration tests remain unqualified coverage, not passing product journeys. The repository-local UV cache was selected for backend checks. No production contract or database schema changed.

An additional `cargo fmt --all -- --check` probe failed exclusively on generator-formatted Rust files, whose formatting differs from rustfmt. It changed no source. Handwritten Rust formatting passes separately. Generated output remains governed by explicit regeneration/drift rather than a manual formatting pass. This optional broad formatting probe is not a passing check or a required verification stage.

The local environment was Darwin 25.3.0 arm64, Node 26.6.0, pnpm 12.4.0, Rust 1.95.0 and uv 0.12.15. Chromium reported 156.0.8078.4. Installed Python consumers ran both 3.11.15, the declared minimum minor, and 3.13.12, the primary repository pin. Both used HTTPX 0.28.1 and Pydantic 2.14.1. Actual runtime facts and archive hashes are recorded in verification artifacts and required by the CI evidence reader.

| Consumed archive | SHA-256 in the final run |
| --- | --- |
| `inframeld-sdk-0.0.0.crate` | `b02f560d584b539c766215121c5dee2e4d88bc4c6398eeaf14a2daf2407998c6` |
| `inframeld-sdk-0.0.0.tgz` | `4de221b74076cea7f0dc16ac8e43d023d0ef044909e6b7ae9c61d2b0b4793cee` |
| `inframeld_sdk-0.0.0-py3-none-any.whl` | `40758d591fabe2b64fcb0721f417893d2ac5b9deb11ff210ffe3d7ab1c0f6d21` |

These identify the tested archives, not a promise of byte-identical native packaging across timestamps or platforms. Source regeneration is the deterministic gate.

## Failure probes and clean bootstrap

Response, protocol, control/witness and lifecycle fixes followed observed failing regressions before implementation. Retained tests reject altered consent inputs, wrong grant status, malformed HTTP-200 bodies, invalid UTF-8/primitives, null/empty required objects, undeclared success, missing bindings/calls/results, duplicates and partial evidence. Valid nullable and bodyless alternatives pass. The Python exact-bodyless-versus-class regression caught response-map ambiguity. A subsequent full run caught missing decoding-context initialization, which was corrected and strengthened with exact-byte/cause assertions before the final passing run.

Actual isolated probes rejected a corrupted cached generator archive and deliberate generated-source drift. The drift run left all 89 tracked source/configuration inputs byte-identical, reported TypeScript failure and continued Rust/Python evaluation. The probe restored the original generated file. Failed patch application remains a retained preparation regression. Repeated current-source preparation applied the actual ordered patch sets successfully.

An actual missing-Chromium run failed TypeScript visibly while Python still ran and passed its selected case. Process/resource regressions exercise stalled startup, live-request cancellation, reuse, failed/denied termination, descendant cleanup, an enclosing Node test-runner timeout, failed browser close and combined execution/cleanup failure. Bounded cleanup attempts all owned resources and cannot turn a failure green. Native Python sync cancellation remains limited to the bridge's actual public capabilities.

A temporary source-only bootstrap copy had no SDK build artifacts or backend implementation. Frozen dependency installation used the pinned Node/pnpm and existing trust policy. Shared TypeScript checks passed before SDK declarations existed. Native TypeScript checks passed after the normal SDK build. Rust built from an empty target directory. Python's standard native frontend built an sdist and wheel from committed source. No generator ran during these builds. The standard Python build frontend came from the isolated development environment, not a new application dependency.

Preservation hashes confirm the root package manifest/lock, production OpenAPI, earlier structured comparison results and pre-existing OpenAPI test changes remained identical to the initial snapshot. Logs, trial material, source snapshots and probe copies stayed temporary or ignored. No permanent evaluation framework was added.

## Independent review and retained regressions

The first independent read-only review reproduced Python primitive coercion, lossy Rust/TypeScript UTF-8 JSON parsing and lost Python raw bytes for undeclared errors. Shared regressions were observed failing before source fixes. A separate resource review reproduced surviving subprocess descendants and identified startup/profile cleanup races and incomplete call evidence. Retained process, browser-resource and evidence-inventory regressions protect those fixes. The reviews used no external CI or product mutations.

Final independent source inspection found no remaining material blocker in the reviewed response-selection/error-context and resource/evidence paths. Reviewers did not execute the final suite, whose results above were personally run by the implementing agent. This is focused independent review, not an assertion that all future contract shapes are qualified.

Five independent read-only fresh-context maintainer trials inspected actual reading routes and returned these results:

| Trial | Outcome |
| --- | --- |
| Add endpoint coverage | Found shared cases, generated native bindings and coverage checks. Its missing Python protocol-Literal documentation route was corrected. |
| Change an existing field | Recognized that operation-ID coverage alone is insufficient, and required reviewing omission/null/type behavior and existing scenarios. |
| Diagnose generator failure/retirement | Preserved provenance and distinguished archive, patch, compilation and behavior failures. Its Python JAR-resource diagnostic mismatch was corrected. |
| Diagnose native typing failure | Found direct generated calls, isolated Python checkers and shared/native TypeScript ordering without coupling Rust/Python to native TypeScript compilation. |
| Unrelated CLI presentation | Used coding/CLI-output guidance and avoided unrelated SDK context or repository edits. |

Synthetic nullable/bodyless fixture operations establish SDK capabilities. They do not claim newly delivered product workflows. Rust binary/streaming/SSE, generator library and metadata-disabled checks remain separate from shared HTTP counts.

## Upgrade rehearsal status

Official upstream metadata read during this task reported Rust `openapi-to-rust` 0.23.0, Hey API 0.99.0 and OpenAPI Generator v7.26.0 as the latest stable releases, matching production pins. Sources: [crates.io metadata](https://crates.io/api/v1/crates/openapi-to-rust), [npm latest metadata](https://registry.npmjs.org/@hey-api/openapi-ts/latest) and [official GitHub release metadata](https://api.github.com/repos/OpenAPITools/openapi-generator/releases/latest). Raw lookup artifacts stayed temporary.

No newer stable release was available for a genuine upgrade rehearsal. Upgrades therefore remain pending. Repeated current-source preparation/regeneration demonstrates current reproducibility, not rebasing or qualifying a newer release. Production pins were not changed.

## Qualification limits and external actions

Linux and remote macOS workflow execution remain pending. Local macOS execution is reported separately. CI was not dispatched, packages were not published and branch rules were not changed. A separate repository-setting action must require the stable `SDK conformance` aggregate. Platform-sensitive process/browser/lifecycle changes now select the macOS matrix alongside generator changes.

A 9/10 qualification claim and issue-closure recommendation require applicable CI evidence and independent review. Controlled collaborators and skipped integration tests do not establish PostgreSQL, real Kratos/Hydra, production CORS or complete CLI/account journeys. Other response modes/protocols and broader concurrency/streaming promises retain their recorded limits. Publication, new public transport-construction APIs and server-version compatibility remain deferred.
