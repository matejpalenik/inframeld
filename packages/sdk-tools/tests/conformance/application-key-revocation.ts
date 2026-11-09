import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const applicationId = "00000000-0000-4000-8000-000000000008";
const keyId = "00000000-0000-4000-8000-000000000010";
const path = {
  project_id: projectId,
  application_principal_id: applicationId,
  key_id: keyId,
};
const route = `/v1/projects/${projectId}/application-accounts/${applicationId}/keys/${keyId}/revoke`;
const body = { expectedAccessRevision: 7 };
const headers = {
  Authorization: "Bearer sdk-human",
  "Idempotency-Key": "sdk-revoke-first",
};
const receipt = {
  operationId: "sdk-application-key-revoke",
  accessRevision: 8,
  idempotencyExpiresAt: "2030-01-02T00:00:00Z",
  metadata: {
    keyId,
    applicationPrincipalId: applicationId,
    projectId,
    prefix: "ifm_app_",
    allowedAdapters: ["http", "mcp"],
    createdAt: "2029-12-31T00:00:00Z",
    expiresAt: "2030-03-31T00:00:00Z",
    revokedAt: "2030-01-01T00:00:00Z",
  },
};

for (const family of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `application-key-revoke-first-${family}`,
      operation: "revokeApplicationKey",
      outcome: "success",
    },
    async ({ call, origin }) => {
      const sent =
        family === "bearer"
          ? headers
          : {
              Cookie: "ory_kratos_session=sdk-cookie",
              Origin: origin,
              "X-Inframeld-CSRF": "1",
              "Idempotency-Key": "sdk-revoke-first",
            };
      const { observation, witness } = await call({
        operation: "revokeApplicationKey",
        path,
        headers: sent,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), receipt);
      assertJsonBody(witness, body);
      assert.equal(witness.path, route);
      assert.equal(witness.query, "");
      assert.equal(
        witness.authorization,
        family === "bearer" ? "Bearer sdk-human" : "",
      );
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-revoke-first");
      assert.equal(
        witness.headers.cookie ?? "",
        family === "cookie" ? "ory_kratos_session=sdk-cookie" : "",
      );
      if (family === "cookie") {
        assert.equal(witness.origin, origin);
        assert.equal(witness.csrf, "1");
      }
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.equal(headerValues(observation, "x-request-id").length, 1);
    },
  );

for (const intent of ["replay", "noop"] as const)
  sdkTest(
    {
      id: `application-key-revoke-${intent}`,
      operation: "revokeApplicationKey",
      outcome: "success",
    },
    async ({ call }) => {
      const input = { expectedAccessRevision: intent === "noop" ? 8 : 7 };
      const { observation, witness } = await call({
        operation: "revokeApplicationKey",
        path,
        headers: { ...headers, "Idempotency-Key": `sdk-revoke-${intent}` },
        body: input,
        timeout: 2000,
      });
      const result = assertSuccess(observation, 200);
      assert.deepEqual(result, {
        ...receipt,
        operationId:
          intent === "noop"
            ? "sdk-application-key-revoke-noop"
            : receipt.operationId,
      });
      assert.equal(Object.hasOwn(result, "key"), false);
      assert.equal(Object.hasOwn(result, "changed"), false);
      assert.equal(Object.hasOwn(result, "secretAvailable"), false);
      assertJsonBody(witness, input);
      assert.equal(witness.authorization, "Bearer sdk-human");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], `sdk-revoke-${intent}`);
      assert.equal(witness.headers.cookie ?? "", "");
    },
  );

sdkTest(
  {
    id: "application-key-revoke-safe-integer-revision",
    operation: "revokeApplicationKey",
    outcome: "success",
  },
  async ({ call }) => {
    const input = { expectedAccessRevision: 9007199254740990 };
    const { observation, witness } = await call({
      operation: "revokeApplicationKey",
      path,
      headers,
      body: input,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      ...receipt,
      accessRevision: 9007199254740991,
    });
    assertJsonBody(witness, input);
  },
);

for (const [name, authorization, status, code] of [
  ["missing", "", 401, "http_error"],
  ["invalid-human", "Bearer wrong-human", 401, "http_error"],
  ["ineligible-human", "Bearer sdk-denied", 403, "access_denied"],
  [
    "unconfirmed-human",
    "Bearer sdk-unavailable",
    503,
    "dependency_unavailable",
  ],
  [
    "application",
    `Bearer ifm_app_00000000-0000-4000-8000-000000000003_${"A".repeat(43)}`,
    403,
    "access_denied",
  ],
] as const)
  sdkTest(
    {
      id: `application-key-revoke-${name}-denied`,
      operation: "revokeApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "revokeApplicationKey",
        path,
        headers: {
          "Idempotency-Key": "sdk-revoke-first",
          ...(authorization ? { Authorization: authorization } : {}),
        },
        body,
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
      assert.equal(witness.authorization, authorization);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers.cookie ?? "", "");
      assert.equal(witness.headers["idempotency-key"], "sdk-revoke-first");
      assertJsonBody(witness, body);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      if (status === 401)
        assert.deepEqual(headerValues(observation, "www-authenticate"), [
          authorization
            ? 'Bearer realm="inframeld", error="invalid_token"'
            : 'Bearer realm="inframeld"',
        ]);
    },
  );

for (const [name, input, target, status, code] of [
  ["stale", { expectedAccessRevision: 6 }, path, 409, "stale_revision"],
  [
    "hidden",
    body,
    { ...path, key_id: "00000000-0000-4000-8000-000000000009" },
    404,
    "resource_not_found",
  ],
] as const)
  sdkTest(
    {
      id: `application-key-revoke-${name}`,
      operation: "revokeApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "revokeApplicationKey",
        path: target,
        headers,
        body: input,
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
      assertJsonBody(witness, input);
      assert.equal(witness.authorization, "Bearer sdk-human");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-revoke-first");
      assert.equal(witness.headers.cookie ?? "", "");
    },
  );

sdkTest(
  {
    id: "application-key-revoke-cookie-csrf-denied",
    operation: "revokeApplicationKey",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "revokeApplicationKey",
      path,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-revoke-first",
      },
      body,
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
    assert.equal(witness.authorization, "");
    assert.equal(witness.csrf, "");
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.equal(witness.headers.cookie, "ory_kratos_session=sdk-cookie");
    assertJsonBody(witness, body);
  },
);

const { metadata: _metadata, ...missingMetadata } = receipt;
for (const [name, invalid] of [
  ["missing-metadata", missingMetadata],
  ["null-metadata", { ...receipt, metadata: null }],
] as const)
  sdkTest(
    {
      id: `application-key-revoke-rejects-${name}`,
      operation: "revokeApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "revokeApplicationKey",
        path,
        headers,
        body,
        timeout: 2000,
        fault: { kind: "json", status: 200, body: invalid },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );

sdkTest(
  {
    id: "application-key-revoke-lost-response-preserves-original-request",
    operation: "revokeApplicationKey",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const original = {
      operation: "revokeApplicationKey" as const,
      path,
      headers,
      body,
      timeout: 2000,
    };
    const results = await sequence([
      { ...original, fault: { kind: "disconnect" } },
      { ...original, fault: { kind: "json", status: 200, body: receipt } },
    ]);
    assert.equal(results[0]!.observation.kind, "sdk-error");
    assert.deepEqual(assertSuccess(results[1]!.observation, 200), receipt);
    for (const { witness } of results) {
      assertJsonBody(witness, body);
      assert.equal(witness.authorization, "Bearer sdk-human");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-revoke-first");
      assert.equal(witness.headers.cookie ?? "", "");
    }
  },
);
