import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

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
