import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  assertJsonBody,
} from "../../src/conformance/assertions.ts";

export const projectId = "00000000-0000-4000-8000-000000000003";
// These caller/transport checks now exercise exact PUT, including delegation.
// The retired POST's false-only response is no longer a live client contract.
export const grantPath = {
  project_id: projectId,
  recipient_principal_id: "00000000-0000-4000-8000-000000000004",
  action_id: "create-access-groups",
};
export const grantInput = { canGrant: true, expectedAccessRevision: 7 };
export const grantResponse = {
  recipientPrincipalId: grantPath.recipient_principal_id,
  actionId: grantPath.action_id,
  accessRevision: 8,
  canGrant: true,
  changed: true,
  operationId: "sdk-project-grant-set",
  projectId,
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
};

for (const [id, credential] of [
  ["grant-bearer", { Authorization: "Bearer sdk-human" }],
  ["grant-cookie", { Cookie: "ory_kratos_session=sdk-cookie" }],
] as const)
  sdkTest(
    { id, operation: "setProjectActionGrant", outcome: "success" },
    async ({ call, origin }) => {
      const headers = {
        ...credential,
        "Idempotency-Key": "sdk-project-grant-key",
        ...("Cookie" in credential
          ? { Origin: origin, "X-Inframeld-CSRF": "1" }
          : {}),
      };
      const { observation, witness } = await call({
        operation: "setProjectActionGrant",
        headers,
        path: grantPath,
        body: grantInput,
        timeout: 2000,
      });
      const body = assertSuccess(observation, 201);
      assert.equal(body.canGrant, true);
      assert.equal(body.accessRevision, 8);
      assert.equal(body.operationId, "sdk-project-grant-set");
      assert.equal(body.changed, true);
      assert.equal(body.projectId, projectId);
      assert.equal(body.recipientPrincipalId, grantPath.recipient_principal_id);
      assert.equal(body.actionId, grantPath.action_id);
      assertJsonBody(witness, grantInput);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-project-grant-key");
    },
  );

for (const [id, revision] of [
  ["grant-invalid", -1],
  ["grant-revision-above-safe-bound", Number.MAX_SAFE_INTEGER + 1],
] as const)
  sdkTest(
    {
      id,
      operation: "setProjectActionGrant",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "setProjectActionGrant",
        headers: {
          Authorization: "Bearer sdk-human",
          "Idempotency-Key": "sdk-project-grant-key",
        },
        path: grantPath,
        body: { ...grantInput, expectedAccessRevision: revision },
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
