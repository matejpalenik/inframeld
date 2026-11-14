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
