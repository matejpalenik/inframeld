# SDK tooling rebuild verification

**Date:** 2026-10-27. Author-run local evidence for [ADR-0092](../../adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md). These results do not replace the earlier generator comparisons or establish remote-platform qualification.

The rebuilt private tooling uses strict TypeScript, Node's test runner, feature-grouped assertions and thin native drivers. Start with the [runbook](../../../packages/sdk-tools/README.md), [endpoint walkthrough](../../../packages/sdk-tools/docs/adding-endpoint.md) or [generator walkthrough](../../../packages/sdk-tools/docs/generators.md).

Subsequent hardening is recorded in the [hardening verification report](sdk-hardening-verification.md). The results below remain dated evidence from the earlier rebuild.

## Environment and inputs

Local execution used Darwin 25.3.0 on arm64, Node 26.6.0, pnpm 12.4.0, Rust 1.95.0, Python 3.13.12 and uv 0.12.15. Selected generator versions remain unchanged. The [manifest](../../../packages/sdk-tools/generators/manifest.json) records their verified archives and ordered patches.

The production schema SHA-256 was `e8b3cb46d7de089319061f7920fec23df1a645401ce8021dfef921d3e174fed0`. Production OpenAPI and the historical comparison result JSON files were unchanged against the pre-migration snapshot. No historical Git revision is claimed for uncommitted work.

## Executed checks

| Check | Observed result |
| --- | --- |
| `CARGO_NET_OFFLINE=true pnpm sdk:verify` | Passed all three SDKs, with a full, unfiltered result inventory. |
| Shared HTTP conformance | 40 cases passed in each of Rust, TypeScript Node/Chromium and Python sync/async, totaling 200 executions with no skipped SDK cases. |
| Tooling | Strict TypeScript checking and 34 behavioral runner/protocol/resource regressions passed. |
| Native models and types | Four Rust model tests, 12 Python model tests and TypeScript negative compilation examples passed. |
| Rust capabilities | 14 synthetic capability tests, 115 available generator library tests and the metadata-disabled external consumer passed. These remain separate from HTTP counts. |
| Reproducibility | Clean temporary regeneration matched committed source and owned dependency declarations for every SDK. |
| Packaging | Rust crate archive, npm tarball and Python sdist/wheel built. Clean external consumers passed without backend, fixture or generator dependencies. TypeScript declarations and Python explicit sync/async closing were checked. |
| Backend contracts | All 27 tests passed, including 14 controlled-router/witness tests and 13 OpenAPI tests. |
| `pnpm check:backend` with the repository-local uv cache | Formatting, lint, strict typing, 1,548 tests and OpenAPI checks passed. 505 integration tests were skipped. |
| `pnpm format:check` with the repository-local uv cache | Passed, including backend Ruff formatting. |
| Skill validation | All five affected SDK/Testing skills passed `skill-creator`'s validator in an isolated PyYAML environment. |

The verification command writes standard test output, JUnit reports, observations and versioned summaries under the ignored `packages/sdk-tools/artifacts/` directory. Temporary runtimes and external consumers are removed after their reports are retained. These local artifacts are not committed evidence or a new evaluation framework.

## Failure evidence retained in behavior

Native model regressions failed before the new generator-input patches. The resulting fixes enforce Rust required-nullable presence and boolean constants, reject explicit null for non-nullable Rust/Python properties, and preserve Python omission instead of substituting defaults or serializing an omitted default. Consent tests check exact decision/remember values. Grant success requires HTTP 201.

Runner tests reject mutated bodies, incorrect method/path or dispatch counts, wrong success statuses, decoding failures under HTTP 200, missing bindings, unknown operations, incomplete/duplicate results and partial CI evidence. Process/deadline tests check nonzero exits, cancellation, stalled responses and execution failures accompanied by cleanup failures. Actual HTTP cases exercise malformed responses, timeouts, lost responses and client reuse after errors.

Additional temporary probes established these failure paths:

- A bad cached archive was rejected before changing generated Rust.
- Deliberate generated-source drift failed checking without modifying the changed source. The probe was then restored.
- Unavailable Chromium failed visibly. Independent Python evaluation still completed in the multi-language failure probe. The selected full Chromium channel was also checked against an empty browser cache.
- SIGINT produced a failed run and closed the active loopback backend. A stalled-startup process reached its deadline and was terminated.
- Stale files seeded into TypeScript `dist` and Python `build/lib` appeared in the former direct build paths. The retained package-consumption checks now reject those files after clean native builds.

Earlier finalization runs exposed two additional problems. Python's source-only generator option omitted `py.typed`, so native selective generation now keeps runtime support and its typing marker while omitting repository/CI templates. The pinned macOS headless-shell browser repeatedly crashed with ICU/GPU errors after a clean download. Playwright's documented [full Chromium headless channel](https://playwright.dev/docs/browsers#chromium-new-headless-mode) passed the lifecycle probe and complete conformance suite. No assertion was weakened and no automatic test retry was introduced.

## Maintainer and documentation checks

Independent read-only trials covered endpoint delivery, generator-failure diagnosis, ordinary Python consumption and an unrelated CLI presentation task. They exposed missing binding-location details, incomplete cache/conflict diagnosis and an incorrect implication of automatic sync-client cleanup. Those routes were corrected and rechecked. The narrow Python question stayed in its language skill, and the CLI task avoided SDK generation context. Trial artifacts remained temporary.

Local Markdown targets and anchors were checked, and the authoritative reading routes were inspected. Discovery metadata remained unchanged. The requirement-to-owner inventory and pre-migration snapshots were temporary migration aids.

## Qualification limits

Linux and remote macOS workflow execution remain pending. CI was not dispatched and branch rules were not changed. Require the stable `SDK conformance` aggregate through a separate repository-setting action.

Skipped integration tests do not establish PostgreSQL, real Kratos/Hydra or complete CLI/account-UI qualification. Controlled HTTP collaborators do not establish production CORS. Synthetic capability schemas do not qualify undelivered product operations. Historical upgrade-rehearsal and unsupported-protocol limits remain in the earlier reports.

Publication, public transport-construction APIs and server-version compatibility remain deferred. SDK identities, version `0.0.0` and publication protection are retained.
