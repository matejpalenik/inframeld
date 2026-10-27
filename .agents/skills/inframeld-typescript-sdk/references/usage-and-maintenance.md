# Consume and maintain the TypeScript client

Alice receives HTTP 200 but the body cannot be decoded as the declared session. A useful SDK failure retains the original response context so she can investigate it without sending another request. The selected Hey API configuration validates selected response bodies with generated Zod schemas and retains raw failure text through a patched Fetch asset.

## Ordinary consumption

The [SDK functions](../../../../packages/sdk-typescript/generated/sdk.gen.ts), [models](../../../../packages/sdk-typescript/generated/types.gen.ts) and [Fetch client](../../../../packages/sdk-typescript/generated/client/client.gen.ts) own implemented signatures. The [outer entry point](../../../../packages/sdk-typescript/index.ts) exports the unpublished package API. Inspect the affected operation rather than assuming another generator's calling convention.

In qualified fields mode, inspect the result's success/error branch and available native `response`. Keep status, headers and body tied to that response. `rawBody` retains exposed JSON/error text when parsing or validation fails. It is a UTF-8 rendering and can contain replacement characters, rather than an exact-byte archive. A 200 status does not override a decoding error. Narrow exported `SdkFailure` by kind. `api.body` is the operation's generated error type only after its declared validator passes. `http.body` stays unknown. `decode` and `request` preserve causes, while `transport.reason` distinguishes network, timeout and caller cancellation. Every branch has a message. Returned hook diagnostics cannot forge a classified failure. A throwing hook creates a request failure whose aggregate cause retains the original classified failure and hook exception.

The selected SDK generation enables response validators and disables request validation. Qualification exercises backend validation responses and native multipart file inputs. Enabling request validators, data-only results, throwing mode or other response parsing choices requires tests for those promises. Their presence as configurable options does not make them qualified public modes.

## Browser and Node behavior

Use caller-configured credentials and base URL. Buffered defaults are five seconds and manual redirects, with no SDK redispatch. Positive finite `timeoutMs` can be configured per client or request. A defined request override wins. The deadline remains active alongside caller cancellation. Explicit transport overrides change the qualified policy. Node tests can supply controlled headers directly. Browser tests use isolated cookie storage, browser-supplied Origin and the fixture's explicit CORS exposure. Code cannot reconstruct a hidden response header or redirect status.

The shared browser redirect case accepts the native opaque response and verifies one dispatch, rather than inventing a 307. This platform distinction does not permit weakening unrelated SDK assertions. Cookie-authenticated writes still follow the backend's CSRF contract. A successful fixture browser run does not implement account login, verify production CORS or establish a complete Studio journey.

## Generation and packaging

The [generator runner](../../../../packages/sdk-tools/src/generation/typescript.ts) owns selected plugin/options configuration. The [tooling package](../../../../packages/sdk-tools/package.json) and lockfile own tool versions. The [patch manifest](../../../../packages/sdk-tools/generators/manifest.json) owns original archive identity and ordered patch digests. Read them when changing generation rather than copying values into this guide.

Ordered patches change privately staged, verified generator and locked shared-parser resources before emission, without modifying installed workspace dependencies. Generated response contracts select exact status before declared class/default and preserve every declared JSON representation and body presence in types and corresponding validators. Exact media types precede wildcards. Required JSON cannot bypass validation through empty responses or supplied content types. Media-type parameters and an unambiguous missing content type are supported. Legitimate nullable/bodyless responses stay distinct, and invalid UTF-8 JSON fails. It does not replace operation generation or add a handwritten HTTP client. Use [shared maintenance](../../inframeld-sdks/references/generator-maintenance.md) for source verification, regression-first fixes, upgrades and retirement. Native typings, generated validators and browser behavior all need review when affected.

The [outer package manifest](../../../../packages/sdk-typescript/package.json) owns private metadata and runtime dependencies. Build committed source into ESM JavaScript and declarations without generation. The runbook's external consumer installs an npm tarball, checks NodeNext declarations and actual public operations, metadata, inspectable errors and recovery, and uses declared dependencies rather than workspace source. Do not import backend packages or generator tooling into application runtime dependencies.

## Evidence and limits

The [report](../../../../docs/development/reports/typescript-python-sdk-generator-comparison.md) and [structured results](../../../../docs/development/reports/typescript-python-sdk-generator-results.json) own dated evidence. Node and Chromium qualification does not establish all Node/browser versions. Linux CI, generator upgrade rehearsal, undeclared error-body validation and the other unqualified modes/protocols retain their recorded limits.

Preserve dated findings. Historical candidate implementations and reproduction tooling are retired under ADR-0091. Publication, an HTTP escape hatch and server-version compatibility remain separate work. The implemented unified SDK gate is described in [shared qualification](../../inframeld-sdks/references/shared-qualification.md). Workflow availability does not establish an executed remote platform result.

Shared tooling checking does not import this driver implementation. Native TypeScript checking runs after SDK declarations build and includes the browser driver, tests and consumer source. Other SDKs still evaluate after a TypeScript compilation failure. See [hardening evidence](../../../../docs/development/reports/sdk-hardening-verification.md) for executed checks and pending platform/upgrade limits.

[ADR-0094](../../../../docs/adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) records failure classification, response variants and transport defaults. The [subsequent evidence](../../../../docs/development/reports/sdk-response-fixes-verification.md) distinguishes executed local checks and review from pending platforms.
