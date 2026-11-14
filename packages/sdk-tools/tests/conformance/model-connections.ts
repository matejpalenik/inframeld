import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const modelConnectionId = "00000000-0000-4000-8000-000000000030";
const root = `/v1/projects/${projectId}/model-connections`;
const path = { project_id: projectId, model_connection_id: modelConnectionId };
const headers = { Authorization: "Bearer sdk-human" };
const request = {
  name: "company-gateway",
  displayName: "Company gateway",
  access: {
    provider: "openai-compatible",
    baseUrl: "https://models.example.test/v1",
    apiVersion: null,
    authentication: "api-key",
  },
};
const item = {
  projectId,
  modelConnectionId,
  ...request,
  connectionAccessRevision: 0,
  credential: { present: false, revision: 0 },
};

sdkTest(
  {
    id: "model-connection-create-original-safe-result",
    operation: "createModelConnection",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "createModelConnection",
      path: { project_id: projectId },
      headers: { ...headers, "Idempotency-Key": "sdk-model-create" },
      body: request,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 201), {
      connection: item,
      operationId: "sdk-model-connection-create",
      idempotencyExpiresAt: "2030-01-01T00:00:00Z",
      projectAccessRevision: 8,
      initialGrants: [
        "view-model-connection-configuration",
        "use-model-connection",
        "manage-model-connection",
        "delete-model-connection",
      ].map((actionId) => ({
        target: { kind: "model-connection", modelConnectionId },
        actionId,
        canGrant: true,
      })),
    });
    assertDispatch(witness, "POST", root);
    assertJsonBody(witness, request);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

for (const read of [
  {
    operation: "getModelConnection",
    route: `${root}/${modelConnectionId}`,
    path,
    expected: item,
  },
  {
    operation: "listModelConnections",
    route: root,
    path: { project_id: projectId },
    query: { limit: 1 },
    expected: { items: [item], nextCursor: null },
  },
  {
    operation: "listModelConnectionUsage",
    route: `${root}/${modelConnectionId}/usage`,
    path,
    query: { limit: 1 },
    expected: { items: [], nextCursor: null },
  },
] as const) {
  sdkTest(
    { id: read.operation, operation: read.operation, outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: read.operation,
        path: read.path,
        ...("query" in read ? { query: read.query } : {}),
        headers,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), read.expected);
      assertDispatch(witness, "GET", read.route);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

const credentialRoute = `${root}/${modelConnectionId}/credential`;
const emptyCredential = {
  projectId,
  modelConnectionId,
  credentialId: null,
  revision: 0,
  present: false,
  changedAt: null,
};
const retainedCredential = {
  ...emptyCredential,
  credentialId: "00000000-0000-4000-8000-000000000031",
  changedAt: "2030-01-01T00:00:00Z",
};
const credentialInput = {
  expectedCredentialRevision: 0,
  value: "synthetic-only-sdk-provider-fixture",
};

sdkTest(
  {
    id: "model-connection-credential-empty-metadata",
    operation: "getModelConnectionCredential",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getModelConnectionCredential",
      path,
      headers,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), emptyCredential);
    assertDispatch(witness, "GET", credentialRoute);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

for (const replayed of [false, true]) {
  sdkTest(
    {
      id: `model-connection-credential-put-${replayed ? "recovered" : "saved"}`,
      operation: "putModelConnectionCredential",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "putModelConnectionCredential",
        path,
        headers: {
          ...headers,
          "Idempotency-Key": replayed
            ? "sdk-credential-replay"
            : "sdk-credential-original",
        },
        body: credentialInput,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), {
        credential: { ...retainedCredential, revision: 1, present: true },
        changed: true,
        replayed,
        operationId: "sdk-model-connection-credential-put",
        idempotencyExpiresAt: "2030-01-01T00:00:00Z",
      });
      assertDispatch(witness, "PUT", credentialRoute);
      const body = witness.jsonBody;
      assert.ok(
        body !== null &&
          typeof body === "object" &&
          !Array.isArray(body) &&
          Object.keys(body).length === 2 &&
          body.expectedCredentialRevision ===
            credentialInput.expectedCredentialRevision &&
          body.value === credentialInput.value,
        "Backend received different credential request fields.",
      );
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

sdkTest(
  {
    id: "model-connection-credential-remove-tombstone",
    operation: "removeModelConnectionCredential",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "removeModelConnectionCredential",
      path,
      headers: { ...headers, "Idempotency-Key": "sdk-credential-remove" },
      query: { expectedCredentialRevision: 1 },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      credential: { ...retainedCredential, revision: 2, present: false },
      changed: true,
      replayed: false,
      operationId: "sdk-model-connection-credential-delete",
      idempotencyExpiresAt: "2030-01-01T00:00:00Z",
    });
    assertDispatch(witness, "DELETE", credentialRoute);
    assert.deepEqual(
      [...new URLSearchParams(String(witness.query))],
      [["expectedCredentialRevision", "1"]],
    );
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "model-connection-credential-stale-remove",
    operation: "removeModelConnectionCredential",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "removeModelConnectionCredential",
      path,
      headers: { ...headers, "Idempotency-Key": "sdk-credential-stale" },
      query: { expectedCredentialRevision: 0 },
      timeout: 2000,
    });
    assertDispatch(witness, "DELETE", credentialRoute);
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 409);
    assert.notEqual(observation.validation, "none");
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.code, "stale_revision");
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);
