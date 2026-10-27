# How SDK tooling fits together

Alice changes the consent endpoint. She needs to regenerate clients and prove that each one sends the intended decision. She should be able to read the consent test without understanding generator installation, wheel packaging or browser startup.

The package separates these responsibilities through ordinary modules. It is development tooling, not another application domain or a reusable orchestration framework.

## Directory map

| Directory/file | Responsibility and dependencies |
| --- | --- |
| [Command entry](../src/cli.ts) | Parse selection, call visible workflows and retain the overall result |
| [Workflows](../src/workflows) | Compose generation, testing and verification stages |
| [Generation](../src/generation) | Verify inputs, apply patches and invoke each concrete generator |
| [Feature tests](../tests/conformance) | Own shared inputs and ordinary assertions grouped by behavior |
| [Conformance support](../src/conformance) | Supply backend/profile fixtures, validate observations and enforce coverage/completeness |
| [Native drivers](../drivers) | Bind protocol operations to public generated SDK calls |
| [Packaging](../src/packaging) | Build archives and verify clean external consumers |
| [System utilities](../src/system) | Bound subprocesses, HTTP/library waits and resource cleanup |
| [CI evidence](../src/ci/evidence.ts) | Check the expected stages, platforms, profiles and complete results |

Workflows depend on these focused modules. Packaging never imports HTTP test execution. Generator preparation never imports conformance. Native SDK packages never import this tooling.

## Follow one test

1. The test command compiles a native driver or bundles the TypeScript driver. This step does not generate SDK source.
2. Node's standard test runner loads [feature cases](../tests/conformance/index.ts). The small [registration helper](../src/conformance/cases.ts) records identity/operation metadata beside each ordinary assertion body.
3. The profile starts production routers with controlled collaborators. Each case and call gets an isolated witness identity. Chromium also gets a fresh browser context per case.
4. The case registers its call identities and explicit faults through private control endpoints, retrieves case-scoped evidence and deletes it after collection. Independent total dispatch counts survive deletion. Fault behavior does not depend on the case's name.
5. The driver invokes public generated APIs. Rust and Python exchange one JSON document on stdin/stdout. Playwright's full Chromium headless channel executes the TypeScript driver in a real page. A call sequence retains one native transport/client pool for lifecycle checks.
6. The parent validates the [versioned protocol](../src/conformance/protocol.ts), checks exact call inventories and inspects independently witnessed dispatches. The feature test asserts its body, headers, status and result.
7. Node reports the test result. JSON observations and JUnit output support CI and diagnosis. Missing results, driver crashes and cleanup failures remain failures.

Tests author meaningful expectations. OpenAPI supplies operation identity, method/path and shapes, but cannot infer the desired business outcome. Agreement between three clients is insufficient evidence.

## Native boundaries

The driver protocol carries profile/case/call identities, generated operation inputs and explicit native success or failure. Results retain validation provenance, body absence versus explicit null and available metadata. Strict Python protocol records reject malformed input, direct sync/async bindings call generated operations, and conversion defects are driver failures. Shared TypeScript checking stays independent of native TypeScript SDK declarations. Raw content and header values carry their encoding. Header arrays preserve repeated values when the native API exposes them. Browser restrictions and native header normalization remain visible.

A driver failure is distinct from an expected SDK error. Invalid envelopes, missing calls and unsupported operations fail. Drivers cannot fill missing data, repair serialization, invent metadata or send fallback requests. Python's deliberate unchecked model construction is restricted to the server-validation case. Other cases use native model validation.

The Rust binding passes `Idempotency-Key` through its generated operation argument rather than adding a second copy as an additional header. This is argument binding, not a serializer workaround. Rust call sequences share a configured transport timeout. Python sync cleanup runs on the generated bridge's event loop.

## Failure and resource ownership

Each process has a deadline and cancellation path. Readiness/control HTTP calls have their own deadlines. The runner owns backend/browser resources and closes them after failure. The fixture runs the prepared backend interpreter in the profile process group. Chromium uses an owned BrowserServer, with forced termination after graceful close fails. Startup owns acquired resources before returning the fixture, and cancellation propagates through control calls, native processes and case contexts. Both the initial failure and a subsequent cleanup failure are retained.

Stages run independently where their inputs permit it. Compilation failure blocks native execution for that SDK, but other SDKs still run. Verification checks archives with native metadata rather than a hardcoded package version.

The [runbook](../README.md) owns commands and caches. [Shared qualification](../../../.agents/skills/inframeld-sdks/references/shared-qualification.md) owns conformance policy. HTTP compatibility and business behavior remain with their existing application/domain owners.

The external patterns behind this design are [Node’s standard test runner](https://nodejs.org/api/test.html), [Playwright browser contexts](https://playwright.dev/docs/browser-contexts) and [Smithy’s explicit HTTP compliance expectations](https://smithy.io/2.0/additional-specs/http-protocol-compliance-tests.html). We use these patterns while retaining OpenAPI and the selected generators.
