# Inframeld TypeScript SDK

The generated client follows Inframeld's native OpenAPI contract. This package remains version `0.0.0` with publication protection. Building or consuming it requires neither the backend nor a generator. Registry publication and server-version compatibility remain separate work.

The ESM package exports generated operations/models, `createClient` and `createConfig`. The qualified mode is Fetch `responseStyle: "fields"` with `throwOnError: false` and generated Zod response validation. Generated operations own their response metadata and validator after caller options, with no response-selection override in ordinary operation options. Exact declared statuses and JSON representations are checked before successful results are returned. Empty required JSON, null for non-nullable responses, invalid UTF-8 and incompatible supplied content types fail with available response context. Missing content type uses the declared representation when unambiguous.

Buffered requests default to `timeoutMs: 5000` and manual redirects. Set a positive finite `timeoutMs` through client or request configuration. A defined request value takes precedence. A caller cancellation signal combines with the deadline. Supply the base URL and credentials. Explicit redirect/transport overrides change the qualified default policy. Fetch does not automatically retry these operations. Inspect `error` independently of HTTP status. A decoding failure can have HTTP 200. `rawBody` is Fetch's UTF-8 text rendering, which can contain replacement characters, rather than an exact-byte archive. Browser rules hide forbidden headers, normalize repeated headers and make manual redirects opaque. Browser cookies require `credentials: "include"` and server-approved Origin/CORS configuration. Other response modes and general streaming behavior remain unqualified.

Narrow the exported `SdkFailure` before reading a problem body:

| `error.kind` | Meaning |
| --- | --- |
| `api` | Declared error body passed its generated validator. Read `error.body` using the operation's error type. |
| `http` | Undeclared status or incompatible representation. A parsed `body` is unknown. |
| `decode` | JSON parsing or schema validation failed. Inspect `cause`. |
| `transport` | Network, timeout or caller cancellation, distinguished by `reason`. |
| `request` | Configuration, construction, serialization or hook failure. Inspect `cause`. |

Every failure has a message. Native HTTP context stays on the fields result. Returned error-hook values can customize diagnostics but cannot replace classification or trusted data. A throwing hook becomes a request failure whose aggregate cause retains the original classified failure and the hook exception. Throwing mode throws that same failure object. Data-only mode still returns undefined on failure. These limited regressions do not qualify every other response mode.

The complete [checked consumer](../sdk-tools/consumers/typescript/main.ts) below runs against the installed tarball. It exercises typed success, metadata and inspectable errors without fallback requests.

## Build and use locally

```sh
pnpm --filter @inframeld/sdk build
cd packages/sdk-typescript
npm pack --ignore-scripts
# In a separate project, install the resulting tarball with npm install /absolute/path/to/archive.tgz
```

Rust/TypeScript consumers take the fixture base URL as their first argument. Python uses the same argument. The examples expect the controlled conformance backend, while application callers supply their own server URL and credentials.

```typescript
/** Public operations from the installed tarball, including error recovery. */
import assert from "node:assert/strict";
import { createClient, getHealth, getCurrentSession } from "@inframeld/sdk";

const client = createClient({ baseUrl: process.argv[2], timeoutMs: 2000 });
const options = {
  client,
  responseStyle: "fields",
  throwOnError: false,
} as const;
const healthy = await getHealth({
  ...options,
  signal: AbortSignal.timeout(2000),
});
assert.ok(healthy.response);
assert.equal(healthy.response.status, 200);
assert.equal(healthy.data?.status, "ok");
const session = await getCurrentSession({
  ...options,
  headers: { Authorization: "Bearer sdk-human" },
  signal: AbortSignal.timeout(2000),
});
assert.equal(session.data?.principalId, "00000000-0000-4000-8000-000000000001");
assert.ok(session.response);
assert.ok(session.response.headers.get("x-request-id"));
const rejected = await getCurrentSession({
  ...options,
  signal: AbortSignal.timeout(2000),
});
assert.ok(rejected.error);
assert.ok(rejected.response);
assert.equal(rejected.response.status, 401);
assert.equal(rejected.error.kind, "api");
assert.ok(rejected.error.kind === "api");
assert.equal(rejected.error.body.status, 401);
assert.ok(rejected.rawBody);
assert.equal(
  (await getHealth({ ...options, signal: AbortSignal.timeout(2000) })).data
    ?.status,
  "ok",
);

console.log(JSON.stringify({ node: process.version }));
```

## Maintain generation

Generation is explicit. Follow the [SDK runbook](../sdk-tools/README.md) for verified inputs, drift, native checks and package consumers. Fixtures and development tooling are outside this distribution. Fix generator source or shipped resources before regeneration, never generated SDK output. See the [response-fix evidence](../../docs/development/reports/sdk-response-fixes-verification.md) for actually executed checks and platform limits.
