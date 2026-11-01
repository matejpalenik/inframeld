import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const organizationId = "00000000-0000-4000-8000-000000000002";
const legacy = "legacy\u0001\n" + "x".repeat(150);
const bearer = { Authorization: "Bearer sdk-human" };
const write = { ...bearer, "Idempotency-Key": "sdk-metadata-key" };
const path = { project_id: projectId };
const metadata = {
  projectId,
  organizationId,
  name: null,
  displayName: legacy,
  metadataRevision: 0,
};
const changed = {
  ...metadata,
  metadataRevision: 1,
  operationId: "sdk-metadata-operation",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
};

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `metadata-read-${credential}`,
      operation: "getProjectMetadata",
      outcome: "success",
    },
    async ({ call }) => {
      const headers =
        credential === "bearer"
          ? bearer
          : { Cookie: "ory_kratos_session=sdk-cookie" };
      const { observation } = await call({
        operation: "getProjectMetadata",
        headers,
        path,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), metadata);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

for (const [id, name] of [
  ["ordinary", "support"],
  ["unreserved", "production"],
  ["minimum", "a"],
  ["maximum", "a".repeat(63)],
] as const)
  sdkTest(
    {
      id: `metadata-resolve-${id}`,
      operation: "resolveProjectName",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "resolveProjectName",
        headers: bearer,
        path: { name },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), { ...metadata, name });
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

for (const [id, replacements] of [
  ["selector-only", { name: "support" }],
  ["label-only", { displayName: "Support" }],
  ["both", { name: "production", displayName: "Production" }],
  ["minimum-label", { displayName: "x" }],
  ["maximum-label", { displayName: "x".repeat(128) }],
  ["non-bmp-label", { displayName: "🧭".repeat(128) }],
  ["combining-label", { displayName: "e\u0301".repeat(64) }],
] as const)
  sdkTest(
    {
      id: `metadata-change-${id}`,
      operation: "updateProjectMetadata",
      outcome: "success",
    },
    async ({ call }) => {
      const body = { expectedMetadataRevision: 0, ...replacements };
      const { observation, witness } = await call({
        operation: "updateProjectMetadata",
        headers: write,
        path,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), {
        ...changed,
        ...replacements,
      });
      assertJsonBody(witness, body);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-metadata-key");
    },
  );

sdkTest(
  {
    id: "metadata-change-cookie",
    operation: "updateProjectMetadata",
    outcome: "success",
  },
  async ({ call, origin }) => {
    const body = { expectedMetadataRevision: 0, name: "support" };
    const { observation, witness } = await call({
      operation: "updateProjectMetadata",
      path,
      body,
      timeout: 2000,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        Origin: origin,
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "sdk-metadata-key",
      },
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      ...changed,
      name: "support",
    });
    assertJsonBody(witness, body);
    assert.equal(witness.origin, origin);
    assert.equal(witness.csrf, "1");
  },
);

for (const [id, body, status] of [
  ["stale", { expectedMetadataRevision: 1, name: "support" }, 409],
  ["empty-change", { expectedMetadataRevision: 0 }, 422],
] as const)
  sdkTest(
    {
      id: `metadata-change-${id}`,
      operation: "updateProjectMetadata",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "updateProjectMetadata",
        headers: write,
        path,
        body,
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assertJsonBody(witness, body);
    },
  );

for (const [id, headers, status] of [
  ["missing-auth", { "Idempotency-Key": "sdk-metadata-key" }, 401],
  ["denied", { ...write, Authorization: "Bearer sdk-denied" }, 403],
  [
    "csrf",
    {
      Cookie: "ory_kratos_session=sdk-cookie",
      "Idempotency-Key": "sdk-metadata-key",
    },
    403,
  ],
] as const)
  sdkTest(
    {
      id: `metadata-change-${id}`,
      operation: "updateProjectMetadata",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "updateProjectMetadata",
        headers,
        path,
        body: { expectedMetadataRevision: 0, name: "support" },
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
    },
  );

for (const [id, invalid] of [
  [
    "missing-name",
    { projectId, organizationId, displayName: legacy, metadataRevision: 0 },
  ],
  ["wrong-revision", { ...metadata, metadataRevision: "0" }],
] as const)
  sdkTest(
    {
      id: `metadata-read-rejects-${id}`,
      operation: "getProjectMetadata",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "getProjectMetadata",
        headers: bearer,
        path,
        timeout: 2000,
        fault: { kind: "json", body: invalid },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );

sdkTest(
  {
    id: "metadata-change-disconnect",
    operation: "updateProjectMetadata",
    outcome: "failure",
  },
  async ({ call }) => {
    const body = { expectedMetadataRevision: 0, name: "support" };
    const { observation, witness } = await call({
      operation: "updateProjectMetadata",
      headers: write,
      path,
      body,
      timeout: 2000,
      fault: { kind: "disconnect" },
    });
    assert.equal(observation.kind, "sdk-error");
    assertJsonBody(witness, body);
  },
);

for (const [id, displayName] of [
  ["empty", ""],
  ["whitespace", "   "],
] as const)
  sdkTest(
    {
      id: `metadata-read-legacy-${id}`,
      operation: "getProjectMetadata",
      outcome: "success",
    },
    async ({ call }) => {
      const expected = { ...metadata, displayName };
      const { observation } = await call({
        operation: "getProjectMetadata",
        headers: bearer,
        path,
        timeout: 2000,
        fault: { kind: "json", body: expected },
      });
      assert.deepEqual(assertSuccess(observation, 200), expected);
    },
  );

sdkTest(
  {
    id: "metadata-change-original-replay",
    operation: "updateProjectMetadata",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const body = { expectedMetadataRevision: 0, name: "support" };
    const input = {
      operation: "updateProjectMetadata" as const,
      headers: write,
      path,
      body,
      timeout: 2000,
    };
    const results = await sequence([input, input]);
    assert.equal(results.length, 2);
    for (const { observation, witness } of results) {
      assert.deepEqual(assertSuccess(observation, 200), {
        ...changed,
        name: "support",
      });
      assertJsonBody(witness, body);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-metadata-key");
    }
  },
);

sdkTest(
  {
    id: "metadata-retired-name-guidance",
    operation: "resolveProjectName",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "resolveProjectName",
      headers: bearer,
      path: { name: "former-support" },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 404);
    assert.notEqual(observation.validation, "none");
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.code, "resource_not_found");
    const detail = observation.body.detail;
    assert.ok(typeof detail === "string");
    assert.ok(detail.includes(projectId));
    assert.ok(detail.includes("support"));
    assert.deepEqual(headerValues(observation, "location"), []);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

for (const status of [413, 415] as const)
  sdkTest(
    {
      id: `metadata-declared-framing-${status}`,
      operation: "updateProjectMetadata",
      outcome: "failure",
    },
    async ({ call }) => {
      const problem = {
        type: "about:blank",
        title: status === 413 ? "Content Too Large" : "Unsupported Media Type",
        status,
        detail: "The request could not be completed.",
        code: "http_error",
        requestId: "00000000-0000-4000-8000-000000000099",
      };
      const body = { expectedMetadataRevision: 0, name: "support" };
      const { observation, witness } = await call({
        operation: "updateProjectMetadata",
        headers: write,
        path,
        body,
        timeout: 2000,
        fault: {
          kind: "json",
          status,
          body: problem,
          contentType: "application/problem+json",
        },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.deepEqual(observation.body, problem);
      assertJsonBody(witness, body);
    },
  );
