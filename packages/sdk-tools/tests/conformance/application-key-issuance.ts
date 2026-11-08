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
const route = `/v1/projects/${projectId}/application-accounts/${applicationId}/keys`;
const path = { project_id: projectId, application_principal_id: applicationId };
const credential = `ifm_app_${keyId}_${"A".repeat(43)}`;
const bearer = { Authorization: "Bearer sdk-human" };
const headers = { ...bearer, "Idempotency-Key": "sdk-key-first" };
const input = { allowedAdapters: ["mcp", "http"], expectedAccessRevision: 7 };
const metadata = {
  keyId,
  applicationPrincipalId: applicationId,
  projectId,
  prefix: "ifm_app_",
  allowedAdapters: input.allowedAdapters,
  createdAt: "2030-01-01T00:00:00Z",
  expiresAt: "2030-04-01T00:00:00Z",
  revokedAt: null,
};
const replay = {
  operationId: "sdk-application-key-issue",
  accessRevision: 8,
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  metadata,
  secretAvailable: false,
};
const first = { ...replay, secretAvailable: true, key: credential };

for (const family of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `application-key-issue-first-${family}`,
      operation: "issueApplicationKey",
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
              "Idempotency-Key": "sdk-key-first",
            };
      const { observation, witness } = await call({
        operation: "issueApplicationKey",
        path,
        headers: sent,
        body: input,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 201), first);
      assertJsonBody(witness, input);
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
      assert.equal(witness.headers["idempotency-key"], "sdk-key-first");
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

for (const adapters of [["http"], ["mcp"], ["http", "mcp"]])
  sdkTest(
    {
      id: `application-key-issue-${adapters.join("-")}-explicit-lifetime`,
      operation: "issueApplicationKey",
      outcome: "success",
    },
    async ({ call }) => {
      const body = {
        ...input,
        allowedAdapters: adapters,
        expiresInSeconds: 60,
      };
      const { observation, witness } = await call({
        operation: "issueApplicationKey",
        path,
        headers,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 201), {
        ...first,
        metadata: {
          ...metadata,
          allowedAdapters: adapters,
          expiresAt: "2030-01-01T00:01:00Z",
        },
      });
      assertJsonBody(witness, body);
    },
  );

sdkTest(
  {
    id: "application-key-issue-safe-original",
    operation: "issueApplicationKey",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "issueApplicationKey",
      path,
      headers: { ...bearer, "Idempotency-Key": "sdk-key-replay" },
      body: input,
      timeout: 2000,
    });
    const result = assertSuccess(observation, 201);
    assert.deepEqual(result, replay);
    assert.equal(Object.hasOwn(result, "key"), false);
    assertJsonBody(witness, input);
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.equal(witness.headers["idempotency-key"], "sdk-key-replay");
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "application-key-issue-safe-integer-revision",
    operation: "issueApplicationKey",
    outcome: "success",
  },
  async ({ call }) => {
    const body = { ...input, expectedAccessRevision: 9007199254740990 };
    const { observation, witness } = await call({
      operation: "issueApplicationKey",
      path,
      headers,
      body,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 201), {
      ...first,
      accessRevision: 9007199254740991,
    });
    assertJsonBody(witness, body);
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
      id: `application-key-issue-${name}-denied`,
      operation: "issueApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "issueApplicationKey",
        path,
        headers: {
          "Idempotency-Key": "sdk-key-first",
          ...(authorization ? { Authorization: authorization } : {}),
        },
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
      assert.equal(witness.authorization, authorization);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers.cookie ?? "", "");
      assertJsonBody(witness, input);
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

for (const [name, body, target, status, code] of [
  [
    "stale",
    { ...input, expectedAccessRevision: 6 },
    path,
    409,
    "stale_revision",
  ],
  [
    "hidden",
    input,
    {
      ...path,
      application_principal_id: "00000000-0000-4000-8000-000000000009",
    },
    404,
    "resource_not_found",
  ],
] as const)
  sdkTest(
    {
      id: `application-key-issue-${name}`,
      operation: "issueApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "issueApplicationKey",
        path: target,
        headers,
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
      assertJsonBody(witness, body);
    },
  );

sdkTest(
  {
    id: "application-key-issue-cookie-csrf-denied",
    operation: "issueApplicationKey",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "issueApplicationKey",
      path,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-key-first",
      },
      body: input,
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
  },
);

const { key: _key, ...missingKey } = first;
const { metadata: _metadata, ...missingMetadata } = replay;
for (const [name, invalid] of [
  ["first-missing-key", missingKey],
  ["replay-missing-metadata", missingMetadata],
  ["string-secret-available", { ...first, secretAvailable: "true" }],
] as const)
  sdkTest(
    {
      id: `application-key-issue-rejects-${name}`,
      operation: "issueApplicationKey",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "issueApplicationKey",
        path,
        headers,
        body: input,
        timeout: 2000,
        fault: { kind: "json", status: 201, body: invalid },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 201);
    },
  );

sdkTest(
  {
    id: "application-key-issue-lost-response-preserves-original-input",
    operation: "issueApplicationKey",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const original = {
      operation: "issueApplicationKey" as const,
      path,
      headers,
      body: input,
      timeout: 2000,
    };
    const results = await sequence([
      { ...original, fault: { kind: "disconnect" } },
      { ...original, fault: { kind: "json", status: 201, body: replay } },
    ]);
    assert.equal(results[0]!.observation.kind, "sdk-error");
    const recovered = assertSuccess(results[1]!.observation, 201);
    assert.deepEqual(recovered, replay);
    assert.equal(Object.hasOwn(recovered, "key"), false);
    for (const { witness } of results) {
      assertJsonBody(witness, input);
      assert.equal(witness.authorization, "Bearer sdk-human");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-key-first");
    }
  },
);
