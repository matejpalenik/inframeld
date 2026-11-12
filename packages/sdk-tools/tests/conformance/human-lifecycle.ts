import assert from "node:assert/strict";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest } from "../../src/conformance/cases.ts";
import type { JsonValue, Observation } from "../../src/conformance/protocol.ts";

const organizationId = "00000000-0000-4000-8000-000000000002";
const principalId = "00000000-0000-4000-8000-00000000000a";
const incompletePrincipalId = "00000000-0000-4000-8000-00000000000b";
const bearer = "Bearer sdk-human";
const cookie = "ory_kratos_session=sdk-cookie";
const path = { organization_id: organizationId, principal_id: principalId };
const targetRoute = (target: string, action: "suspend" | "restore") =>
  `/v1/organizations/${organizationId}/humans/${target}/${action}`;

const original = { organizationId, principalId, accessRevision: 8 };
const suspend = {
  operation: "suspendHuman",
  action: "suspend",
  key: "sdk-suspend-original",
  status: 202,
  input: { expectedAccessRevision: 7, reason: "Security review" },
  receipt: {
    ...original,
    operationId: "sdk-human-suspension",
    idempotencyExpiresAt: null,
    accessBlocked: true,
    cleanupOperationId: "sdk-human-suspension-cleanup",
  },
} as const;
const restore = {
  operation: "restoreHuman",
  action: "restore",
  key: "sdk-restore-original",
  status: 200,
  input: { expectedAccessRevision: 7, securityReviewReference: "review-188" },
  receipt: {
    ...original,
    operationId: "sdk-human-restoration",
    idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  },
} as const;

function assertLifecycleWitness(
  witness: Record<string, JsonValue>,
  route: string,
  body: Record<string, JsonValue>,
  headers: Record<string, string>,
): void {
  assertDispatch(witness, "POST", route);
  assert.equal(witness.query, "");
  assertJsonBody(witness, body);
  assert.ok(typeof witness.rawBodyBase64 === "string");
  const wireBody: unknown = JSON.parse(
    Buffer.from(witness.rawBodyBase64, "base64").toString("utf8"),
  );
  assert.deepEqual(wireBody, body);
  assert.deepEqual(witness.idempotencyKeys, [headers["Idempotency-Key"]]);
  assert.equal(witness.authorization, headers.Authorization ?? "");
  if (headers.Origin !== undefined)
    assert.equal(witness.origin, headers.Origin);
  assert.equal(witness.csrf, headers["X-Inframeld-CSRF"] ?? "");
  assert.ok(
    witness.headers &&
      typeof witness.headers === "object" &&
      !Array.isArray(witness.headers),
  );
  assert.equal(witness.headers["idempotency-key"], headers["Idempotency-Key"]);
  assert.equal(witness.headers.cookie ?? "", headers.Cookie ?? "");
}

function assertLifecycleProblem(
  observation: Observation,
  status: number,
  code: string,
): void {
  assert.equal(observation.kind, "sdk-error");
  assert.equal(observation.status, status);
  assert.ok(
    ["generated-model", "generated-schema"].includes(observation.validation),
  );
  assert.ok(
    observation.body &&
      typeof observation.body === "object" &&
      !Array.isArray(observation.body),
  );
  assert.equal(observation.body.status, status);
  assert.equal(observation.body.code, code);
  assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
}

for (const { operation, action, key, status, input, receipt } of [
  suspend,
  restore,
]) {
  sdkTest(
    {
      id: `human-lifecycle-${action}-replay`,
      operation,
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ sequence, origin }) => {
      const headers: Record<string, string> = {
        "Idempotency-Key": key,
        ...(action === "suspend"
          ? { Authorization: bearer }
          : { Cookie: cookie, Origin: origin, "X-Inframeld-CSRF": "1" }),
      };
      const call = { operation, path, headers, body: input, timeout: 2000 };
      const results = await sequence([call, call]);
      for (const { observation, witness } of results) {
        assert.deepEqual(assertSuccess(observation, status), receipt);
        assert.deepEqual(headerValues(observation, "cache-control"), [
          "no-store",
        ]);
        assertLifecycleWitness(
          witness,
          targetRoute(principalId, action),
          input,
          headers,
        );
      }
    },
  );
  sdkTest(
    {
      id: `human-lifecycle-${action}-csrf-denied`,
      operation,
      outcome: "failure",
    },
    async ({ call, origin }) => {
      const headers = {
        Cookie: cookie,
        Origin: origin,
        "Idempotency-Key": key,
      };
      const { observation, witness } = await call({
        operation,
        path,
        headers,
        body: input,
        timeout: 2000,
      });
      assertLifecycleProblem(observation, 403, "access_denied");
      assertLifecycleWitness(
        witness,
        targetRoute(principalId, action),
        input,
        headers,
      );
    },
  );
}

sdkTest(
  {
    id: "human-lifecycle-restore-cleanup-incomplete",
    operation: restore.operation,
    outcome: "failure",
  },
  async ({ call }) => {
    const headers = {
      Authorization: bearer,
      "Idempotency-Key": "sdk-restore-cleanup-incomplete",
    };
    const { observation, witness } = await call({
      operation: restore.operation,
      path: { ...path, principal_id: incompletePrincipalId },
      headers,
      body: restore.input,
      timeout: 2000,
    });
    assertLifecycleProblem(observation, 409, "conflict");
    assertLifecycleWitness(
      witness,
      targetRoute(incompletePrincipalId, "restore"),
      restore.input,
      headers,
    );
  },
);
