import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  assertJsonBody,
} from "../../src/conformance/assertions.ts";

export const projectId = "00000000-0000-4000-8000-000000000003";
export const grantInput = {
  recipientPrincipalId: "00000000-0000-4000-8000-000000000002",
  actionId: "create-access-groups",
  expectedAccessRevision: 0,
};
export const grantResponse = {
  recipientPrincipalId: grantInput.recipientPrincipalId,
  actionId: grantInput.actionId,
  accessRevision: 1,
  canGrant: false,
  operationId: "sdk-operation",
  projectId,
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
};

for (const [id, credential] of [
  ["grant-bearer", { Authorization: "Bearer sdk-human" }],
  ["grant-cookie", { Cookie: "ory_kratos_session=sdk-cookie" }],
] as const)
  sdkTest(
    { id, operation: "assignProjectUseOnlyGrant", outcome: "success" },
    async ({ call, origin }) => {
      const headers = {
        ...credential,
        "Idempotency-Key": "sdk-key",
        ...("Cookie" in credential
          ? { Origin: origin, "X-Inframeld-CSRF": "1" }
          : {}),
      };
      const { observation, witness } = await call({
        operation: "assignProjectUseOnlyGrant",
        headers,
        path: { project_id: projectId },
        body: grantInput,
        timeout: 2000,
      });
      const body = assertSuccess(observation, 201);
      assert.equal(body.canGrant, false);
      assert.equal(body.accessRevision, 1);
      assert.equal(body.operationId, "sdk-operation");
      assert.equal(body.projectId, projectId);
      assert.equal(body.recipientPrincipalId, grantInput.recipientPrincipalId);
      assert.equal(body.actionId, grantInput.actionId);
      assertJsonBody(witness, grantInput);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-key");
    },
  );

sdkTest(
  {
    id: "grant-invalid",
    operation: "assignProjectUseOnlyGrant",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "assignProjectUseOnlyGrant",
      headers: {
        Authorization: "Bearer sdk-human",
        "Idempotency-Key": "sdk-key",
      },
      path: { project_id: projectId },
      body: { ...grantInput, expectedAccessRevision: -1 },
      uncheckedModel: true,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 422);
    assert.notEqual(observation.validation, "none");
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    const issues = observation.body.errors;
    assert.ok(Array.isArray(issues));
    const issue = issues[0];
    assert.ok(issue && typeof issue === "object" && !Array.isArray(issue));
    assert.equal(issue.code, "out_of_range");
    assert.equal(issue.location, "body");
    assert.deepEqual(issue.path, []);
  },
);
