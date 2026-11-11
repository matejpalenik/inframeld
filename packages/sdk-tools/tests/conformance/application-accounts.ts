import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const applicationId = "00000000-0000-4000-8000-000000000008";
const existingId = "00000000-0000-4000-8000-000000000009";
const keyId = "00000000-0000-4000-8000-000000000010";
const root = `/v1/projects/${projectId}/application-accounts`;
const bearer = { Authorization: "Bearer sdk-human" };
const write = { ...bearer, "Idempotency-Key": "sdk-account-create" };
const input = {
  name: "support-bot",
  displayName: "SupportBot 🧭",
  expectedAccessRevision: 7,
};
const receipt = {
  operationId: "sdk-application-account-create",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  projectId,
  principalId: applicationId,
  name: input.name,
  displayName: input.displayName,
  accessRevision: 8,
  initialGrants: [
    "issue-application-keys",
    "revoke-application-keys",
    "delete-application-account",
  ].map((actionId) => ({
    target: {
      kind: "application-account",
      projectId,
      applicationPrincipalId: applicationId,
    },
    actionId,
    canGrant: true,
  })),
};
const metadata = {
  projectId,
  principalId: applicationId,
  name: "support-bot",
  displayName: "SupportBot",
  status: "active",
  createdAt: "2030-01-01T00:00:00Z",
  accessRevision: 8,
};
const key = {
  keyId,
  applicationPrincipalId: existingId,
  projectId,
  prefix: "ifm_app_",
  allowedAdapters: ["http", "mcp"],
  createdAt: "2030-01-01T00:00:00Z",
  expiresAt: "2030-04-01T00:00:00Z",
  revokedAt: null,
};

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `application-account-create-${credential}`,
      operation: "createApplicationAccount",
      outcome: "success",
    },
    async ({ call, origin }) => {
      const headers =
        credential === "bearer"
          ? write
          : {
              Cookie: "ory_kratos_session=sdk-cookie",
              Origin: origin,
              "X-Inframeld-CSRF": "1",
              "Idempotency-Key": "sdk-account-create",
            };
      const { observation, witness } = await call({
        operation: "createApplicationAccount",
        path: { project_id: projectId },
        headers,
        body: input,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 201), receipt);
      assertJsonBody(witness, input);
      assert.equal(witness.path, root);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-account-create");
      if (credential === "cookie") {
        assert.equal(witness.origin, origin);
        assert.equal(witness.csrf, "1");
      }
    },
  );

sdkTest(
  {
    id: "application-account-original-request-is-preserved",
    operation: "createApplicationAccount",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const original = {
      operation: "createApplicationAccount" as const,
      path: { project_id: projectId },
      headers: write,
      body: input,
      timeout: 2000,
    };
    const results = await sequence([original, original]);
    for (const { observation, witness } of results) {
      assert.deepEqual(assertSuccess(observation, 201), receipt);
      assertJsonBody(witness, input);
    }
  },
);

sdkTest(
  {
    id: "application-account-safe-integer-revision",
    operation: "createApplicationAccount",
    outcome: "success",
  },
  async ({ call }) => {
    const body = { ...input, expectedAccessRevision: 9007199254740990 };
    const { observation, witness } = await call({
      operation: "createApplicationAccount",
      path: { project_id: projectId },
      headers: write,
      body,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 201), {
      ...receipt,
      accessRevision: 9007199254740991,
    });
    assertJsonBody(witness, body);
  },
);

sdkTest(
  {
    id: "application-account-get-exact-principal",
    operation: "getApplicationAccount",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getApplicationAccount",
      path: { project_id: projectId, application_principal_id: applicationId },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), metadata);
    assert.equal(witness.path, `${root}/${applicationId}`);
  },
);

sdkTest(
  {
    id: "application-account-resolve-exact-name",
    operation: "resolveApplicationAccount",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "resolveApplicationAccount",
      path: { project_id: projectId },
      query: { name: "support-bot" },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), metadata);
    assert.equal(
      new URLSearchParams(witness.query as string).get("name"),
      "support-bot",
    );
    assert.equal(witness.path, `${root}/resolve`);
  },
);

sdkTest(
  {
    id: "application-account-legacy-null-name",
    operation: "getApplicationAccount",
    outcome: "success",
  },
  async ({ call }) => {
    const legacy = { ...metadata, name: null, displayName: " old\nlabel " };
    const { observation } = await call({
      operation: "getApplicationAccount",
      path: { project_id: projectId, application_principal_id: applicationId },
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: legacy },
    });
    assert.deepEqual(assertSuccess(observation, 200), legacy);
  },
);

sdkTest(
  {
    id: "application-account-empty-key-page",
    operation: "listApplicationKeys",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listApplicationKeys",
      path: { project_id: projectId, application_principal_id: applicationId },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [],
      nextCursor: null,
    });
    assert.equal(witness.query, "");
  },
);

sdkTest(
  {
    id: "application-key-bounded-first-page",
    operation: "listApplicationKeys",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listApplicationKeys",
      path: { project_id: projectId, application_principal_id: existingId },
      query: { limit: 1 },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [key],
      nextCursor: "Y29udGludWU",
    });
    assert.equal(
      new URLSearchParams(witness.query as string).get("limit"),
      "1",
    );
  },
);

sdkTest(
  {
    id: "application-key-explicit-continuation",
    operation: "listApplicationKeys",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listApplicationKeys",
      path: { project_id: projectId, application_principal_id: existingId },
      query: { limit: 1, cursor: "Y29udGludWU" },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [{ ...key, keyId: "00000000-0000-4000-8000-000000000011" }],
      nextCursor: null,
    });
    assert.equal(
      new URLSearchParams(witness.query as string).get("cursor"),
      "Y29udGludWU",
    );
  },
);

sdkTest(
  {
    id: "application-key-get-safe-metadata",
    operation: "getApplicationKey",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getApplicationKey",
      path: {
        project_id: projectId,
        application_principal_id: existingId,
        key_id: keyId,
      },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), key);
    assert.equal(witness.path, `${root}/${existingId}/keys/${keyId}`);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "application-account-cookie-csrf-denied",
    operation: "createApplicationAccount",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "createApplicationAccount",
      path: { project_id: projectId },
      body: input,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-account-create",
      },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
  },
);

sdkTest(
  {
    id: "application-account-name-missing",
    operation: "resolveApplicationAccount",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "resolveApplicationAccount",
      path: { project_id: projectId },
      query: { name: "not-present" },
      headers: bearer,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 404);
    assert.notEqual(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "application-key-missing",
    operation: "getApplicationKey",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getApplicationKey",
      path: {
        project_id: projectId,
        application_principal_id: applicationId,
        key_id: keyId,
      },
      headers: bearer,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 404);
    assert.notEqual(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "application-key-invalid-prefix-is-rejected",
    operation: "getApplicationKey",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getApplicationKey",
      path: {
        project_id: projectId,
        application_principal_id: existingId,
        key_id: keyId,
      },
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: { ...key, prefix: "wrong_" } },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
  },
);

sdkTest(
  {
    id: "application-account-missing-required-nullable-name",
    operation: "getApplicationAccount",
    outcome: "failure",
  },
  async ({ call }) => {
    const { name: _name, ...missing } = metadata;
    const { observation } = await call({
      operation: "getApplicationAccount",
      path: { project_id: projectId, application_principal_id: applicationId },
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: missing },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
  },
);

const deletionPath = {
  project_id: projectId,
  application_principal_id: applicationId,
};
const deletionQuery = { expectedAccessRevision: 7 };
const deletionKey = "sdk-application-account-delete";
const deletionReceipt = {
  operationId: deletionKey,
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  projectId,
  principalId: applicationId,
  accessRevision: 8,
  accessBlocked: true,
};

function assertDeletionWitness(witness: Record<string, JsonValue>) {
  assertDispatch(witness, "DELETE", root + "/" + applicationId);
  assert.deepEqual(
    [...new URLSearchParams(String(witness.query))],
    [["expectedAccessRevision", "7"]],
  );
  assert.equal(witness.rawBodyBase64, "");
  assert.ok(
    witness.headers &&
      typeof witness.headers === "object" &&
      !Array.isArray(witness.headers),
  );
  assert.equal(witness.headers["idempotency-key"], deletionKey);
  return witness.headers;
}

sdkTest(
  {
    id: "application-account-delete-browser",
    operation: "deleteApplicationAccount",
    outcome: "success",
  },
  async ({ call, origin }) => {
    const { observation, witness } = await call({
      operation: "deleteApplicationAccount",
      path: deletionPath,
      query: deletionQuery,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        Origin: origin,
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": deletionKey,
      },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), deletionReceipt);
    const witnessedHeaders = assertDeletionWitness(witness);
    assert.equal(witnessedHeaders.cookie, "ory_kratos_session=sdk-cookie");
    assert.equal(witness.origin, origin);
    assert.equal(witness.csrf, "1");
    assert.equal(witness.authorization, "");
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "application-account-delete-denied-other-human",
    operation: "deleteApplicationAccount",
    outcome: "failure",
  },
  async ({ call }) => {
    const authorization = "Bearer sdk-other-human";
    const { observation, witness } = await call({
      operation: "deleteApplicationAccount",
      path: deletionPath,
      query: deletionQuery,
      headers: {
        Authorization: authorization,
        "Idempotency-Key": deletionKey,
      },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
    assert.ok(
      ["generated-model", "generated-schema"].includes(observation.validation),
    );
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.status, 403);
    assert.equal(observation.body.code, "access_denied");
    for (const field of Object.keys(deletionReceipt))
      assert.equal(Object.hasOwn(observation.body, field), false);
    const witnessedHeaders = assertDeletionWitness(witness);
    assert.equal(witnessedHeaders.cookie, undefined);
    assert.equal(witness.authorization, authorization);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);
