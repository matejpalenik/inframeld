import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

// Fixed private fixture inputs, not an issuance or persisted-key verification recipe.
const applicationKey = (suffix: string) =>
  `ifm_app_00000000-0000-4000-8000-${suffix}_${"A".repeat(43)}`;
const applicationIdentity = {
  principalId: "00000000-0000-4000-8000-000000000008",
  projectId: "00000000-0000-4000-8000-000000000003",
};

sdkTest(
  {
    id: "application-session-success",
    operation: "getCurrentApplicationSession",
    outcome: "success",
  },
  async ({ call }) => {
    const credential = applicationKey("000000000003");
    const { observation, witness } = await call({
      operation: "getCurrentApplicationSession",
      headers: { Authorization: `Bearer ${credential}` },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), applicationIdentity);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
    assert.equal(headerValues(observation, "x-request-id").length, 1);
    assert.equal(witness.method, "GET");
    assert.equal(witness.path, "/v1/application-session");
    assert.equal(witness.query, "");
    assert.equal(witness.rawBodyBase64, "");
    assert.equal(witness.authorization, `Bearer ${credential}`);
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.ok(!Object.hasOwn(witness.headers, "idempotency-key"));
    assert.equal(witness.headers.cookie, undefined);
    assert.ok(!Object.hasOwn(witness, "jsonBody"));
  },
);

for (const [id, headers, status, code] of [
  ["missing", {}, 401, "http_error"],
  ["human-bearer", { Authorization: "Bearer sdk-human" }, 401, "http_error"],
  [
    "human-cookie",
    { Cookie: "ory_kratos_session=sdk-cookie" },
    401,
    "http_error",
  ],
  [
    "unknown-key",
    { Authorization: `Bearer ${applicationKey("000000000099")}` },
    401,
    "http_error",
  ],
  [
    "local-denied",
    { Authorization: `Bearer ${applicationKey("000000000004")}` },
    403,
    "access_denied",
  ],
  [
    "unconfirmed",
    { Authorization: `Bearer ${applicationKey("000000000005")}` },
    503,
    "dependency_unavailable",
  ],
  [
    "revoked-at-disclosure",
    { Authorization: `Bearer ${applicationKey("000000000007")}` },
    401,
    "http_error",
  ],
  [
    "suspended-at-disclosure",
    { Authorization: `Bearer ${applicationKey("000000000009")}` },
    403,
    "access_denied",
  ],
  [
    "competing",
    {
      Authorization: `Bearer ${applicationKey("000000000003")}`,
      Cookie: "ory_kratos_session=sdk-cookie",
    },
    400,
    "invalid_authentication_request",
  ],
] as const)
  sdkTest(
    {
      id: `application-session-${id}`,
      operation: "getCurrentApplicationSession",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "getCurrentApplicationSession",
        headers,
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(observation.body.code, code);
      assert.equal(typeof observation.body.requestId, "string");
      assert.deepEqual(headerValues(observation, "x-request-id"), [
        observation.body.requestId,
      ]);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      const authorization =
        "Authorization" in headers ? headers.Authorization : "";
      const cookie = "Cookie" in headers ? headers.Cookie : undefined;
      const challenge =
        status === 400
          ? 'Bearer realm="inframeld", error="invalid_request"'
          : status === 401
            ? authorization
              ? 'Bearer realm="inframeld", error="invalid_token"'
              : 'Bearer realm="inframeld"'
            : undefined;
      assert.deepEqual(
        headerValues(observation, "www-authenticate"),
        challenge ? [challenge] : [],
      );
      assert.ok(!JSON.stringify(observation.body).includes("ifm_app_"));
      assert.equal(witness.method, "GET");
      assert.equal(witness.path, "/v1/application-session");
      assert.equal(witness.query, "");
      assert.equal(witness.rawBodyBase64, "");
      assert.equal(witness.authorization, authorization);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers.authorization, authorization || undefined);
      assert.equal(witness.headers.cookie, cookie);
    },
  );

sdkTest(
  {
    id: "application-session-replacement-identity",
    operation: "getCurrentApplicationSession",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const results = await sequence(
      ["000000000003", "000000000006"].map((suffix) => ({
        operation: "getCurrentApplicationSession" as const,
        headers: { Authorization: `Bearer ${applicationKey(suffix)}` },
        timeout: 2000,
      })),
    );
    for (const result of results)
      assert.deepEqual(
        assertSuccess(result.observation, 200),
        applicationIdentity,
      );
    assert.equal(
      results[0]!.witness.authorization,
      `Bearer ${applicationKey("000000000003")}`,
    );
    assert.equal(
      results[1]!.witness.authorization,
      `Bearer ${applicationKey("000000000006")}`,
    );
  },
);

sdkTest(
  {
    id: "application-session-reuse-no-fallback",
    operation: "getCurrentApplicationSession",
    outcome: "success",
    expectedCalls: 3,
  },
  async ({ sequence }) => {
    const [application, human, anonymous] = await sequence([
      {
        operation: "getCurrentApplicationSession",
        headers: { Authorization: `Bearer ${applicationKey("000000000003")}` },
        timeout: 2000,
      },
      {
        operation: "getCurrentApplicationSession",
        headers: { Authorization: "Bearer sdk-human" },
        timeout: 2000,
      },
      { operation: "getCurrentApplicationSession", headers: {}, timeout: 2000 },
    ]);
    assert.deepEqual(
      assertSuccess(application!.observation, 200),
      applicationIdentity,
    );
    assert.equal(human!.observation.kind, "sdk-error");
    assert.equal(human!.observation.status, 401);
    assert.equal(
      application!.witness.authorization,
      `Bearer ${applicationKey("000000000003")}`,
    );
    assert.equal(human!.witness.authorization, "Bearer sdk-human");
    assert.deepEqual(headerValues(human!.observation, "www-authenticate"), [
      'Bearer realm="inframeld", error="invalid_token"',
    ]);
    assert.equal(anonymous!.observation.kind, "sdk-error");
    assert.equal(anonymous!.observation.status, 401);
    assert.equal(anonymous!.witness.authorization, "");
    assert.deepEqual(headerValues(anonymous!.observation, "www-authenticate"), [
      'Bearer realm="inframeld"',
    ]);
    for (const result of [application!, human!, anonymous!]) {
      const headers = result.witness.headers;
      assert.ok(
        headers && typeof headers === "object" && !Array.isArray(headers),
      );
      assert.equal(headers.cookie, undefined);
    }
  },
);

sdkTest(
  {
    id: "human-session-rejects-application-key",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getCurrentSession",
      headers: { Authorization: `Bearer ${applicationKey("000000000003")}` },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 401);
    assert.equal(
      witness.authorization,
      `Bearer ${applicationKey("000000000003")}`,
    );
    assert.deepEqual(headerValues(observation, "www-authenticate"), [
      'Bearer realm="inframeld", error="invalid_token"',
    ]);
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.equal(witness.headers.cookie, undefined);
  },
);

sdkTest(
  { id: "health", operation: "getHealth", outcome: "success" },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getHealth",
      headers: {},
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), { status: "ok" });
  },
);

for (const [id, headers] of [
  ["session-bearer", { Authorization: "Bearer sdk-human" }],
  ["session-cookie", { Cookie: "ory_kratos_session=sdk-cookie" }],
] as const)
  sdkTest(
    { id, operation: "getCurrentSession", outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "getCurrentSession",
        headers,
        timeout: 2000,
      });
      assert.equal(
        assertSuccess(observation, 200).principalId,
        "00000000-0000-4000-8000-000000000001",
      );
      if ("Authorization" in headers)
        assert.equal(witness.authorization, headers.Authorization);
    },
  );

for (const [id, headers, status] of [
  ["missing-auth", {}, 401],
  ["invalid-auth", { Authorization: "Bearer invalid" }, 401],
  ["denied", { Authorization: "Bearer sdk-denied" }, 403],
  ["unavailable", { Authorization: "Bearer sdk-unavailable" }, 503],
  [
    "competing",
    {
      Authorization: "Bearer sdk-human",
      Cookie: "ory_kratos_session=sdk-cookie",
    },
    400,
  ],
] as const)
  sdkTest(
    { id, operation: "getCurrentSession", outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation: "getCurrentSession",
        headers,
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(typeof observation.body.requestId, "string");
      if (id === "competing")
        assert.equal(observation.body.code, "invalid_authentication_request");
    },
  );

sdkTest(
  {
    id: "response-headers",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 401);
    assert.ok(
      headerValues(observation, "www-authenticate").some((value) =>
        value.includes("Bearer"),
      ),
    );
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.deepEqual(headerValues(observation, "x-request-id"), [
      observation.body.requestId,
    ]);
  },
);

sdkTest(
  { id: "success-headers", operation: "getHealth", outcome: "success" },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getHealth",
      headers: {},
      timeout: 2000,
    });
    assertSuccess(observation, 200);
    assert.equal(headerValues(observation, "x-request-id").length, 1);
  },
);

sdkTest(
  {
    id: "reuse-without-previous-credentials",
    operation: "getCurrentSession",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const [authenticated, anonymous] = await sequence([
      {
        operation: "getCurrentSession",
        headers: { Authorization: "Bearer sdk-human" },
        timeout: 2000,
      },
      { operation: "getCurrentSession", headers: {}, timeout: 2000 },
    ]);
    assertSuccess(authenticated!.observation, 200);
    assert.equal(anonymous!.observation.kind, "sdk-error");
    assert.equal(anonymous!.observation.status, 401);
    assert.equal(anonymous!.witness.authorization, "");
  },
);
