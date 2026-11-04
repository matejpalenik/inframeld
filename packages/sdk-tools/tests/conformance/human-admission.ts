import assert from "node:assert/strict";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest } from "../../src/conformance/cases.ts";
import { budgets } from "../../src/system/budgets.ts";

const organizationId = "00000000-0000-4000-8000-000000000002";
const bob = "00000000-0000-4000-8000-000000000004";
const existingHuman = "00000000-0000-4000-8000-000000000005";
const path = { organization_id: organizationId };
const route = `/v1/organizations/${organizationId}/human-admissions`;
const body = { identityId: bob, expectedAccessRevision: 7 };
const unchangedBody = { ...body, identityId: existingHuman };
const bearer = {
  Authorization: "Bearer sdk-human",
  "Idempotency-Key": "sdk-admit-key",
};
const created = {
  operationId: "sdk-human-admission",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  organizationId,
  principalId: bob,
  accessRevision: 8,
  changed: true,
};
const unchanged = {
  ...created,
  principalId: existingHuman,
  accessRevision: 7,
  changed: false,
};

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `human-admission-${credential}`,
      operation: "admitHuman",
      outcome: "success",
    },
    async ({ call, origin }) => {
      const headers =
        credential === "bearer"
          ? bearer
          : {
              Cookie: "ory_kratos_session=sdk-cookie",
              Origin: origin,
              "X-Inframeld-CSRF": "1",
              "Idempotency-Key": "sdk-admit-key",
            };
      const { observation, witness } = await call({
        operation: "admitHuman",
        path,
        body,
        headers,
        timeout: budgets.case,
      });
      assert.deepEqual(assertSuccess(observation, 201), created);
      assertDispatch(witness, "POST", route);
      assertJsonBody(witness, body);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      const requestIds = headerValues(observation, "x-request-id");
      assert.equal(requestIds.length, 1);
      assert.match(
        requestIds[0] ?? "",
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      );
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-admit-key");
      if (credential === "cookie") {
        assert.equal(witness.origin, origin);
        assert.equal(witness.csrf, "1");
      }
    },
  );

sdkTest(
  {
    id: "human-admission-already-admitted",
    operation: "admitHuman",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "admitHuman",
      path,
      body: unchangedBody,
      headers: bearer,
      timeout: budgets.case,
    });
    assert.deepEqual(assertSuccess(observation, 200), unchanged);
    assertDispatch(witness, "POST", route);
    assertJsonBody(witness, unchangedBody);
  },
);

// These controlled original outcomes qualify client reuse, not database replay.
for (const [status, input, expected] of [
  [201, body, created],
  [200, unchangedBody, unchanged],
] as const)
  sdkTest(
    {
      id: `human-admission-original-${status}`,
      operation: "admitHuman",
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ sequence }) => {
      const call = {
        operation: "admitHuman" as const,
        path,
        body: input,
        headers: bearer,
        timeout: budgets.case,
      };
      const results = await sequence([call, call]);
      assert.equal(results.length, 2);
      for (const { observation, witness } of results) {
        assert.deepEqual(assertSuccess(observation, status), expected);
        assertDispatch(witness, "POST", route);
        assertJsonBody(witness, input);
      }
    },
  );

const failures: {
  id: string;
  headers: Record<string, string>;
  status: number;
  code: string;
  organization?: string;
  revision?: number;
}[] = [
  {
    id: "cookie-csrf",
    headers: {
      Cookie: "ory_kratos_session=sdk-cookie",
      "Idempotency-Key": "sdk-admit-key",
    },
    status: 403,
    code: "access_denied",
  },
  {
    id: "unauthenticated",
    headers: { "Idempotency-Key": "sdk-admit-key" },
    status: 401,
    code: "http_error",
  },
  {
    id: "application-key-denied",
    headers: { ...bearer, Authorization: "Bearer ifm_app_unsupported" },
    status: 401,
    code: "http_error",
  },
  {
    id: "forbidden",
    headers: { ...bearer, Authorization: "Bearer sdk-denied" },
    status: 403,
    code: "access_denied",
  },
  {
    id: "hidden-org",
    headers: bearer,
    status: 404,
    code: "resource_not_found",
    organization: "00000000-0000-4000-8000-000000000099",
  },
  {
    id: "stale",
    headers: bearer,
    status: 409,
    code: "stale_revision",
    revision: 0,
  },
  {
    id: "unavailable",
    headers: { ...bearer, Authorization: "Bearer sdk-unavailable" },
    status: 503,
    code: "dependency_unavailable",
  },
];
for (const failure of failures)
  sdkTest(
    {
      id: `human-admission-${failure.id}`,
      operation: "admitHuman",
      outcome: "failure",
    },
    async ({ call }) => {
      const organization = failure.organization ?? organizationId;
      const input = { ...body, expectedAccessRevision: failure.revision ?? 7 };
      const { observation, witness } = await call({
        operation: "admitHuman",
        path: { organization_id: organization },
        body: input,
        headers: failure.headers,
        timeout: budgets.case,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, failure.status);
      assert.notEqual(observation.validation, "none");
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(observation.body.code, failure.code);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assertDispatch(
        witness,
        "POST",
        `/v1/organizations/${organization}/human-admissions`,
      );
      assertJsonBody(witness, input);
    },
  );

sdkTest(
  {
    id: "human-admission-declared-validation-problem",
    operation: "admitHuman",
    outcome: "failure",
  },
  async ({ call }) => {
    const problem = {
      type: "https://api.test/problems/validation",
      title: "Request validation failed",
      status: 422,
      detail: "The request is invalid.",
      code: "validation_error",
      requestId: "00000000-0000-4000-8000-000000000099",
    };
    const { observation, witness } = await call({
      operation: "admitHuman",
      path,
      body,
      headers: bearer,
      timeout: budgets.case,
      fault: {
        kind: "json",
        status: 422,
        body: problem,
        contentType: "application/problem+json",
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 422);
    assert.notEqual(observation.validation, "none");
    assert.deepEqual(observation.body, problem);
    assertJsonBody(witness, body);
  },
);

for (const [id, status, input, malformed] of [
  [
    "missing-principal",
    201,
    body,
    {
      operationId: created.operationId,
      idempotencyExpiresAt: created.idempotencyExpiresAt,
      organizationId,
      accessRevision: 8,
      changed: true,
    },
  ],
  [
    "null-expiry",
    200,
    unchangedBody,
    { ...unchanged, idempotencyExpiresAt: null },
  ],
] as const)
  sdkTest(
    {
      id: `human-admission-rejects-${id}`,
      operation: "admitHuman",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "admitHuman",
        path,
        body: input,
        headers: bearer,
        timeout: budgets.case,
        fault: { kind: "json", status, body: malformed },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.ok(observation.raw);
      assertDispatch(witness, "POST", route);
      assertJsonBody(witness, input);
    },
  );
