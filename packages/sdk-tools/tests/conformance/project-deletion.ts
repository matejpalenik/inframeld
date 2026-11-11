import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const route = `/v1/projects/${projectId}`;
const path = { project_id: projectId };
const query = { expectedAccessRevision: 7 };
const headers = {
  Authorization: "Bearer sdk-human",
  "Idempotency-Key": "sdk-project-delete",
};
const receipt = {
  operationId: "sdk-project-delete",
  idempotencyExpiresAt: null,
  projectId,
  accessRevision: 8,
  admissionConfirmed: true,
  accessBlocked: true,
};
function assertDeleteWitness(
  witness: Record<string, JsonValue>,
  key: string,
): void {
  assertDispatch(witness, "DELETE", route);
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
  assert.equal(witness.headers["idempotency-key"], key);
}

sdkTest(
  {
    id: "project-deletion-admission-replay-disconnect",
    operation: "deleteProject",
    outcome: "success",
    expectedCalls: 3,
  },
  async ({ sequence }) => {
    const original = {
      operation: "deleteProject" as const,
      path,
      query,
      headers,
      timeout: 2000,
    };
    const results = await sequence([
      original,
      original,
      { ...original, fault: { kind: "disconnect" } },
    ]);
    for (const index of [0, 1]) {
      const result = results[index]!;
      assert.deepEqual(assertSuccess(result.observation, 202), receipt);
      assert.deepEqual(headerValues(result.observation, "cache-control"), [
        "no-store",
      ]);
    }
    assert.equal(results[2]!.observation.kind, "sdk-error");
    for (const result of results) {
      assertDeleteWitness(result.witness, headers["Idempotency-Key"]);
      assert.equal(result.witness.authorization, headers.Authorization);
    }
  },
);

sdkTest(
  {
    id: "project-deletion-cookie",
    operation: "deleteProject",
    outcome: "success",
  },
  async ({ call, origin }) => {
    const { observation, witness } = await call({
      operation: "deleteProject",
      path,
      query,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        Origin: origin,
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": headers["Idempotency-Key"],
      },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 202), receipt);
    assertDeleteWitness(witness, headers["Idempotency-Key"]);
    assert.equal(witness.authorization, "");
    assert.equal(witness.origin, origin);
    assert.equal(witness.csrf, "1");
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.equal(witness.headers.cookie, "ory_kratos_session=sdk-cookie");
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

for (const [id, authorization, key, revision, target, status, code] of [
  [
    "missing-credential",
    "",
    headers["Idempotency-Key"],
    7,
    projectId,
    401,
    "http_error",
  ],
  [
    "denied",
    "Bearer sdk-denied",
    headers["Idempotency-Key"],
    7,
    projectId,
    403,
    "access_denied",
  ],
  [
    "hidden",
    headers.Authorization,
    headers["Idempotency-Key"],
    7,
    "00000000-0000-4000-8000-000000000099",
    404,
    "resource_not_found",
  ],
  [
    "stale",
    headers.Authorization,
    headers["Idempotency-Key"],
    6,
    projectId,
    409,
    "stale_revision",
  ],
  [
    "fresh-blocked",
    headers.Authorization,
    "sdk-project-delete-fresh",
    7,
    projectId,
    409,
    "conflict",
  ],
  [
    "unavailable",
    headers.Authorization,
    "sdk-project-delete-unavailable",
    7,
    projectId,
    503,
    "dependency_unavailable",
  ],
] as const)
  sdkTest(
    {
      id: `project-deletion-${id}`,
      operation: "deleteProject",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "deleteProject",
        path: { project_id: target },
        query: { expectedAccessRevision: revision },
        headers: {
          "Idempotency-Key": key,
          ...(authorization ? { Authorization: authorization } : {}),
        },
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.ok(
        ["generated-model", "generated-schema"].includes(
          observation.validation,
        ),
      );
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(observation.body.status, status);
      assert.equal(observation.body.code, code);
      assertDispatch(witness, "DELETE", `/v1/projects/${target}`);
      assert.equal(witness.rawBodyBase64, "");
      assert.deepEqual(
        [...new URLSearchParams(String(witness.query))],
        [["expectedAccessRevision", String(revision)]],
      );
      assert.equal(witness.authorization, authorization);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

sdkTest(
  {
    id: "project-deletion-cookie-csrf-denied",
    operation: "deleteProject",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "deleteProject",
      path,
      query,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": headers["Idempotency-Key"],
      },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.code, "access_denied");
    assertDeleteWitness(witness, headers["Idempotency-Key"]);
    assert.equal(witness.authorization, "");
    assert.equal(witness.csrf, "");
  },
);

const { idempotencyExpiresAt: _expiry, ...missingExpiry } = receipt;
sdkTest(
  {
    id: "project-deletion-rejects-missing-required-expiry",
    operation: "deleteProject",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "deleteProject",
      path,
      query,
      headers,
      timeout: 2000,
      fault: { kind: "json", status: 202, body: missingExpiry },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 202);
    assert.ok(observation.raw);
    assertDeleteWitness(witness, headers["Idempotency-Key"]);
  },
);

// Valid native parameter types cannot express every rejected raw query spelling.
sdkTest(
  {
    id: "project-deletion-typed-validation-problem",
    operation: "deleteProject",
    outcome: "failure",
  },
  async ({ call }) => {
    const body = {
      type: "https://inframeld.dev/problems/validation-error",
      title: "Validation failed",
      status: 422,
      detail: "The request does not satisfy the operation contract.",
      code: "validation_error",
      requestId: "00000000-0000-4000-8000-000000000099",
    };
    const { observation, witness } = await call({
      operation: "deleteProject",
      path,
      query,
      headers,
      timeout: 2000,
      fault: {
        kind: "raw",
        status: 422,
        contentType: "application/problem+json",
        bodyBase64: Buffer.from(JSON.stringify(body)).toString("base64"),
        headers: [["Cache-Control", "no-store"]],
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 422);
    assert.ok(
      ["generated-model", "generated-schema"].includes(observation.validation),
    );
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.status, 422);
    assert.equal(observation.body.code, body.code);
    assertDeleteWitness(witness, headers["Idempotency-Key"]);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);
