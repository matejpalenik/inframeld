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
| [Process owner](../src/system/process_owner.py) | Retain one target and signal its owned group before the final reap |
| [Native browser fixture](../tests/native/fixtures/browser-owner.ts) | Retain the actual BrowserServer outside native test workers and distinguish production completion from emergency recovery |
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

Suppose a command's leader exits while a descendant keeps running. Node may already have reaped that leader before delivering its exit callback. A later signal to its saved numeric process group would no longer have retained identity. The tooling therefore separates stream handling from wait ownership.

[Node process handling](../src/system/process.ts) owns execution/startup deadlines, bounded target streams, logs and error presentation. `startProcess` returns an `OwnedProcess` handle with cached finalization. Its PID is diagnostic only. The private standard-library [Python owner](../src/system/process_owner.py), running under host Python 3.13, starts one target in a new session and is its sole waiter. Reaping collects a child's final exit status and releases its process identity. The owner observes exit through `waitid` with `WNOWAIT`, which leaves the leader available to wait for without reaping it. Natural exit starts descendant cleanup immediately without waiting for output EOF. Only this owner signals the retained target group. It disables further signalling before the final `waitpid`, and lost wait ownership cannot be recovered from a numeric ID.

The helper's fd 3 carries a strict, versioned UTF-8 JSON control protocol, separate from the SDK driver protocol. Target stdin/stdout/stderr remain byte streams on their own descriptors, and the target never inherits control. START carries the merged target environment and original deadlines. STOP requests the same finalization once. A conservative monotonic-clock mapping avoids assuming that Node and Python clocks share an epoch. The start document is capped at 1 MiB. Other frames are capped at 16 KiB, while Node bounds buffered control input to 64 KiB and at most five records. Control waits are clipped to the existing lifecycle deadline. Invalid, truncated or missing terminal evidence fails rather than becoming an empty successful result. Implemented fields and limits belong to the two source modules, not a second public protocol.

Cleanup retains the first stop deadline across repeated close, cancellation, overflow and control events. A bounded checked `ps` observation distinguishes executable group members from defunct entries. Failed or malformed observations mean unknown, and a successful signal alone is not cleanup evidence. The same-group guarantee does not cover detached work or require every orphan zombie to disappear. A missing owner or failed reap forbids any later numeric signalling. EOF can trigger the helper's bounded fallback, but cannot grant its enclosing caller extra time or retroactively establish a missing receipt.

The [backend fixture](../src/conformance/backend.ts) acquires this owned target using the prepared backend interpreter. Its session is separate from the profile controller. In ordinary shared conformance, the [profile](../src/conformance/profile.ts) separately owns Playwright's BrowserServer and web listener. It caches one disposal path, bounds backend, browser and listener disposal by the enclosing allowance, and preserves each failure. BrowserServer uses its own close/kill API, with close and forced kill sharing the browser's allocation. Even a successful kill retains the earlier graceful-close error. Losing the profile controller does not let an outer process infer browser completion from backend group cleanup.

Native browser-resource tests add a separate [fixture launcher](../tests/native/fixtures/browser-owner.ts), outside the Node test-controller and worker sessions. It retains the real BrowserServer object and pending launch promise. Test profiles use a limited adapter for `wsEndpoint`, `close` and `kill`, while fixed private IPC requests only launch, close and kill. The adapter does not transfer the actual browser handle to a worker. Owner receipts require actual API completion and observed server closure, rather than a request acknowledgement or a child-written success flag.

The launcher runs its worker-loss probe before native/profile cases. Its independent recovery protects the fixture when a worker dies, but recovery-origin evidence cannot become profile-origin completion. A late browser acquisition retains the original failure and recovery deadline. Opaque acquisition or loss of the launcher itself can leave resources unknown and held. Whole-owner death with a real browser is not a supported failure injection without separately recoverable isolation. This fixed fixture is private qualification tooling, not a general process broker or a product API. The [runbook](../README.md#commands) owns invocation guidance, and source or pure fixture tests alone do not establish native browser qualification.

Startup owns acquired resources before returning a fixture, and cancellation propagates through control calls, native processes and case contexts. A target result, terminal owner evidence, successful helper completion and stream completion are distinct requirements. The helper's exit code is not the target's result. Initial failures and subsequent cleanup/control/log failures remain inspectable together. The [runbook's budgets and diagnosis](../README.md#resource-budgets-and-protocol-evidence) explain operating limits. The [qualification policy](../../../.agents/skills/inframeld-sdks/references/shared-qualification.md#process-ownership-and-cleanup-evidence) owns the conditions for accepting cleanup evidence.

Stages run independently where their inputs permit it. Compilation failure blocks native execution for that SDK, but other SDKs still run. Verification checks archives with native metadata rather than a hardcoded package version.

The [runbook](../README.md) owns commands and caches. [Shared qualification](../../../.agents/skills/inframeld-sdks/references/shared-qualification.md) owns conformance policy. HTTP compatibility and business behavior remain with their existing application/domain owners.

The external patterns behind this design are [Node’s standard test runner](https://nodejs.org/api/test.html), [Playwright browser contexts](https://playwright.dev/docs/browser-contexts) and [Smithy’s explicit HTTP compliance expectations](https://smithy.io/2.0/additional-specs/http-protocol-compliance-tests.html). We use these patterns while retaining OpenAPI and the selected generators.

Path witnesses retain the raw percent-encoded request path separately from ASGI routing interpretation. This preserves evidence for slash and percent escaping instead of comparing a decoded path to an encoded expectation.
