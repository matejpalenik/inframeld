import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const unsetId = "00000000-0000-4000-8000-000000000005";
const b = "00000000-0000-4000-8000-000000000020";
const c = "00000000-0000-4000-8000-000000000030";
const path = { project_id: projectId };
const route = "/v1/projects/" + projectId + "/upload-defaults";
const headers = {
  Authorization: "Bearer sdk-human",
  "Idempotency-Key": "sdk-upload-first",
};
const body = { groupIds: [b], expectedAccessRevision: 7 };
const receipt = {
  projectId,
  accessRevision: 8,
  groupIds: [b],
  operationId: "sdk-upload-original",
  idempotencyExpiresAt: "2030-01-02T00:00:00Z",
};

for (const family of ["bearer", "cookie"] as const) {
  sdkTest(
    {
      id: "upload-defaults-read-" + family,
      operation: "getProjectUploadDefaults",
      outcome: "success",
    },
    async ({ call, origin }) => {
      const sent: Record<string, string> =
        family === "bearer"
          ? { Authorization: "Bearer sdk-human" }
          : { Cookie: "ory_kratos_session=sdk-cookie", Origin: origin };
      const { observation, witness } = await call({
        operation: "getProjectUploadDefaults",
        path,
        headers: sent,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), {
        projectId,
        accessRevision: 9,
        groupIds: [c],
      });
      assert.equal(witness.method, "GET");
      assert.equal(witness.path, route);
      assert.equal(witness.query, "");
      assert.equal(witness.rawBodyBase64, "");
      assert.equal(
        witness.authorization,
        family === "bearer" ? "Bearer sdk-human" : "",
      );
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(
        witness.headers.cookie ?? "",
        family === "cookie" ? "ory_kratos_session=sdk-cookie" : "",
      );
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
  sdkTest(
    {
      id: "upload-defaults-set-" + family,
      operation: "setProjectUploadDefaults",
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
              "Idempotency-Key": "sdk-upload-first",
            };
      const { observation, witness } = await call({
        operation: "setProjectUploadDefaults",
        path,
        headers: sent,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), receipt);
      assertJsonBody(witness, body);
      assert.equal(witness.method, "PUT");
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
      assert.equal(witness.headers["idempotency-key"], "sdk-upload-first");
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
}

sdkTest(
  {
    id: "upload-defaults-unconfigured-read",
    operation: "getProjectUploadDefaults",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getProjectUploadDefaults",
      path: { project_id: unsetId },
      headers: { Authorization: "Bearer sdk-human" },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      projectId: unsetId,
      accessRevision: 7,
      groupIds: null,
    });
    assert.equal(witness.path, "/v1/projects/" + unsetId + "/upload-defaults");
    assert.equal(witness.rawBodyBase64, "");
  },
);

for (const [intent, input, key, expected] of [
  [
    "canonical-set",
    { groupIds: [c, b], expectedAccessRevision: 7 },
    "sdk-upload-first",
    { ...receipt, groupIds: [b, c] },
  ],
  [
    "fresh-noop",
    { groupIds: [c], expectedAccessRevision: 9 },
    "sdk-upload-noop",
    {
      ...receipt,
      groupIds: [c],
      accessRevision: 9,
      operationId: "sdk-upload-noop",
    },
  ],
  ["historical-replay", body, "sdk-upload-replay", receipt],
  [
    "safe-integer-revision",
    { ...body, expectedAccessRevision: 9007199254740990 },
    "sdk-upload-first",
    { ...receipt, accessRevision: 9007199254740991 },
  ],
] satisfies Array<
  [
    string,
    { groupIds: string[]; expectedAccessRevision: number },
    string,
    typeof receipt,
  ]
>)
  sdkTest(
    {
      id: "upload-defaults-" + intent,
      operation: "setProjectUploadDefaults",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "setProjectUploadDefaults",
        path,
        headers: { ...headers, "Idempotency-Key": key },
        body: input,
        timeout: 2000,
      });
      const result = assertSuccess(observation, 200);
      assert.deepEqual(result, expected);
      assert.equal(Object.hasOwn(result, "beforeGroupIds"), false);
      assertJsonBody(witness, input);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], key);
      assert.equal(witness.authorization, "Bearer sdk-human");
      assert.equal(witness.path, route);
    },
  );

for (const [name, authorization, status, code] of [
  ["missing", "", 401, "http_error"],
  ["invalid-human", "Bearer wrong-human", 401, "http_error"],
  [
    "application",
    "Bearer ifm_app_00000000-0000-4000-8000-000000000003_" + "A".repeat(43),
    403,
    "access_denied",
  ],
  [
    "unconfirmed-human",
    "Bearer sdk-unavailable",
    503,
    "dependency_unavailable",
  ],
] as const)
  sdkTest(
    {
      id: "upload-defaults-" + name + "-denied",
      operation: "setProjectUploadDefaults",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "setProjectUploadDefaults",
        path,
        headers: {
          "Idempotency-Key": "sdk-upload-first",
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
      assertJsonBody(witness, body);
      assert.equal(witness.authorization, authorization);
      assert.equal(witness.path, route);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-upload-first");
      if (status === 401)
        assert.deepEqual(headerValues(observation, "www-authenticate"), [
          authorization
            ? 'Bearer realm="inframeld", error="invalid_token"'
            : 'Bearer realm="inframeld"',
        ]);
    },
  );

for (const [name, key, input, target, status, code] of [
  [
    "stale",
    "sdk-upload-first",
    { ...body, expectedAccessRevision: 6 },
    path,
    409,
    "stale_revision",
  ],
  ["expired-original", "sdk-upload-expired", body, path, 409, "conflict"],
  [
    "unknown-commit",
    "sdk-upload-unknown",
    body,
    path,
    503,
    "dependency_unavailable",
  ],
  [
    "old-group-authority-lost",
    "sdk-upload-denied-old",
    body,
    path,
    403,
    "access_denied",
  ],
  [
    "new-group-authority-lost",
    "sdk-upload-denied-new",
    body,
    path,
    403,
    "access_denied",
  ],
  [
    "retained-group-authority-lost",
    "sdk-upload-denied-retained",
    body,
    path,
    403,
    "access_denied",
  ],
  [
    "hidden-project",
    "sdk-upload-first",
    body,
    { project_id: "00000000-0000-4000-8000-000000000099" },
    404,
    "resource_not_found",
  ],
] as const)
  sdkTest(
    {
      id: "upload-defaults-" + name,
      operation: "setProjectUploadDefaults",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "setProjectUploadDefaults",
        path: target,
        headers: { ...headers, "Idempotency-Key": key },
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
      assert.equal(witness.headers["idempotency-key"], key);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

sdkTest(
  {
    id: "upload-defaults-cookie-csrf-denied",
    operation: "setProjectUploadDefaults",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "setProjectUploadDefaults",
      path,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-upload-first",
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
    assertJsonBody(witness, body);
    assert.equal(witness.authorization, "");
    assert.equal(witness.csrf, "");
  },
);

for (const [name, operation, invalid] of [
  [
    "read-missing-groups",
    "getProjectUploadDefaults",
    { projectId, accessRevision: 9 },
  ],
  [
    "change-null-groups",
    "setProjectUploadDefaults",
    { ...receipt, groupIds: null },
  ],
] as const)
  sdkTest(
    { id: "upload-defaults-rejects-" + name, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        path,
        headers,
        ...(operation === "setProjectUploadDefaults" ? { body } : {}),
        timeout: 2000,
        fault: { kind: "json", status: 200, body: invalid },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );

sdkTest(
  {
    id: "upload-defaults-lost-response-preserves-original-request",
    operation: "setProjectUploadDefaults",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    // Controlled response loss proves client/wire behavior, not a physical COMMIT acknowledgement fault.
    const original = {
      operation: "setProjectUploadDefaults" as const,
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
      assert.equal(witness.headers["idempotency-key"], "sdk-upload-first");
      assert.equal(witness.path, route);
    }
  },
);
