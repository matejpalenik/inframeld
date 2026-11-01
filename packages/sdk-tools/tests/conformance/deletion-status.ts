import assert from "node:assert/strict";
import { sdkTest, type CaseCall } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const operation = "getDeletionStatus";
const headers = { Authorization: "Bearer sdk-human" };
const original = "settled +/&é";
const retained = {
  outcome: "retained",
  operationId: original,
  jobState: "succeeded",
  admissionConfirmed: true,
  accessBlocked: true,
  applicationShutdownComplete: true,
  physicalCleanupComplete: true,
  retentionExpiresAt: "2030-01-01T00:00:00Z",
};
const active = {
  ...retained,
  operationId: "active",
  jobState: "running",
  applicationShutdownComplete: false,
  physicalCleanupComplete: null,
  retentionExpiresAt: null,
};
const unknown = {
  ...retained,
  operationId: "unknown",
  jobState: null,
  admissionConfirmed: null,
  accessBlocked: null,
  applicationShutdownComplete: null,
  physicalCleanupComplete: null,
  retentionExpiresAt: null,
};

for (const [id, operationId, expected] of [
  ["settled", original, retained],
  ["active", "active", active],
  ["unknown", "unknown", unknown],
  ["missing", "missing", { outcome: "unresolved" }],
  ["expired", "expired", { outcome: "unresolved" }],
  ["noninitiator", "foreign", { outcome: "unresolved" }],
] as const) {
  sdkTest(
    { id: `deletion-status-${id}`, operation, outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation,
        headers,
        query: { operationId },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), expected);
      assertDispatch(witness, "GET", "/v1/deletions/status");
      assert.deepEqual(
        [...new URLSearchParams(String(witness.query))],
        [["operationId", operationId]],
      );
      assert.equal(witness.rawBodyBase64, "");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

sdkTest(
  { id: "deletion-status-cookie", operation, outcome: "success" },
  async ({ call }) => {
    const { observation } = await call({
      operation,
      headers: { Cookie: "ory_kratos_session=sdk-cookie" },
      query: { operationId: original },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), retained);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

for (const [id, credentials, operationId, status] of [
  ["missing-credential", {}, original, 401],
  ["invalid-credential", { Authorization: "Bearer invalid" }, original, 401],
  ["ineligible", { Authorization: "Bearer sdk-denied" }, original, 403],
  [
    "authentication-unavailable",
    { Authorization: "Bearer sdk-unavailable" },
    original,
    503,
  ],
  ["lookup-unavailable", headers, "unavailable", 503],
  ["invalid-reference", headers, " ", 422],
  [
    "competing-credentials",
    { ...headers, Cookie: "ory_kratos_session=sdk-cookie" },
    original,
    400,
  ],
] as const) {
  sdkTest(
    { id: `deletion-status-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers: credentials,
        query: { operationId },
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

for (const field of Object.keys(retained)) {
  const body: Record<string, JsonValue> = { ...retained };
  delete body[field];
  sdkTest(
    {
      id: `deletion-status-rejects-missing-${field}`,
      operation,
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers,
        query: { operationId: original },
        timeout: 2000,
        fault: { kind: "json", body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );
}

for (const [id, body] of [
  ["outcome", { ...retained, outcome: "erased" }],
  ["job-state", { ...retained, jobState: "complete" }],
  ["boolean", { ...retained, accessBlocked: "false" }],
  ["expiry", { ...retained, retentionExpiresAt: "tomorrow" }],
  ["null-identity", { ...retained, operationId: null }],
] as const) {
  sdkTest(
    { id: `deletion-status-rejects-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers,
        query: { operationId: original },
        timeout: 2000,
        fault: { kind: "json", body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );
}

sdkTest(
  {
    id: "deletion-status-client-reuse",
    operation,
    outcome: "success",
    expectedCalls: 5,
  },
  async ({ sequence }) => {
    const results = await sequence([
      {
        operation,
        headers,
        query: { operationId: original },
        timeout: 2000,
        fault: { kind: "json", body: { ...retained, jobState: "complete" } },
      },
      ...[original, "active", "unknown", "foreign"].map(
        (operationId): CaseCall => ({
          operation,
          headers,
          query: { operationId },
          timeout: 2000,
        }),
      ),
    ]);
    assert.equal(results[0]!.observation.kind, "sdk-error");
    assert.equal(results[0]!.observation.status, 200);
    assert.ok(results[0]!.observation.raw);
    for (const [index, expected] of [
      retained,
      active,
      unknown,
      { outcome: "unresolved" },
    ].entries()) {
      const { observation, witness } = results[index + 1]!;
      assert.deepEqual(assertSuccess(observation, 200), expected);
      assertDispatch(witness, "GET", "/v1/deletions/status");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);
