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
