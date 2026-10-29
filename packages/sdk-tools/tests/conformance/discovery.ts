import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

for (const [operation, suffix, id] of [
  ["getProtectedResourceMetadata", "", "root"],
  ["getProtectedResourceMetadataForPath", "/api/v1", "path"],
  ["getProtectedResourceMetadataForPath", "/api/", "trailing"],
  ["getProtectedResourceMetadataForPath", "/a%20b", "space"],
  ["getProtectedResourceMetadataForPath", "/api%2Fv1", "encoded-slash"],
  ["getProtectedResourceMetadataForPath", "/a%25b", "percent"],
] as const) {
  sdkTest(
    {
      id: `discovery-${id}`,
      operation,
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation,
        headers: {},
        timeout: 2000,
        ...(suffix ? { path: { resource_path: suffix.slice(1) } } : {}),
      });
      assert.deepEqual(assertSuccess(observation, 200), {
        resource: `https://api.test${suffix}`,
        authorization_servers: ["https://auth.test/"],
        scopes_supported: ["inframeld:api"],
        bearer_methods_supported: ["header"],
        inframeld: {
          schema_version: 1,
          client_id: "inframeld-cli",
          installation_id: "00000000-0000-4000-8000-000000000001",
        },
      });
      assert.equal(
        witness.path,
        `/.well-known/oauth-protected-resource${suffix}`,
      );
      assert.ok(!witness.authorization);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

for (const operation of [
  "getProtectedResourceMetadata",
  "getProtectedResourceMetadataForPath",
] as const) {
  sdkTest(
    { id: `discovery-malformed-${operation}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers: {},
        timeout: 2000,
        ...(operation.endsWith("ForPath")
          ? { path: { resource_path: "api" } }
          : {}),
        fault: { kind: "malformed" },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );
}
