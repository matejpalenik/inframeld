import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { CaseCall } from "../../src/conformance/cases.ts";
import { payload } from "./schema.ts";
import { grantInput, projectId } from "./grants.ts";

const rawText = (
  raw: { encoding: "utf8" | "base64"; value: string } | undefined,
) =>
  raw?.encoding === "base64"
    ? Buffer.from(raw.value, "base64").toString("utf8")
    : raw?.value;
for (const [id, fault, body] of [
  ["malformed-success", { kind: "malformed" }, "{"],
  [
    "invalid-shape",
    { kind: "json", body: { principalId: 123 } },
    '{"principalId":123}',
  ],
  ["missing-field", { kind: "json", body: {} }, "{}"],
  ["unexpected-status", { kind: "unexpected" }, '{"unrecognized":true}'],
] as const)
  sdkTest(
    { id, operation: "getCurrentSession", outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation: "getCurrentSession",
        headers: {},
        timeout: 2000,
        fault,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, id === "unexpected-status" ? 418 : 200);
      assert.equal(rawText(observation.raw), body);
      assert.deepEqual(headerValues(observation, "x-request-id"), [
        "00000000-0000-4000-8000-000000000099",
      ]);
    },
  );

sdkTest(
  {
    id: "invalid-scalar",
    operation: "contractFixturePayload",
    outcome: "failure",
  },
  async ({ call }) => {
    const invalid = {
      required_name: 123,
      required_nullable: null,
      score: "wrong",
      choice: [],
    };
    const { observation } = await call({
      operation: "contractFixturePayload",
      headers: {},
      body: payload,
      timeout: 2000,
      fault: { kind: "json", body: invalid },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
    assert.equal(rawText(observation.raw), JSON.stringify(invalid));
    assert.deepEqual(headerValues(observation, "x-request-id"), [
      "00000000-0000-4000-8000-000000000099",
    ]);
  },
);
sdkTest(
  { id: "redirect", operation: "getHealth", outcome: "failure" },
  async ({ call, profile }) => {
    const { observation } = await call({
      operation: "getHealth",
      headers: {},
      timeout: 2000,
      fault: { kind: "redirect" },
    });
    assert.equal(observation.kind, "sdk-error");
    if (profile === "typescript-chromium") {
      assert.equal(observation.status, 0);
      assert.equal(observation.responseType, "opaqueredirect");
    } else assert.equal(observation.status, 307);
  },
);
sdkTest(
  { id: "timeout", operation: "getCurrentSession", outcome: "failure" },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 100,
      fault: { kind: "slow" },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.match(JSON.stringify(observation), /timeout|timed.?out/i);
  },
);
sdkTest(
  {
    id: "lost-response",
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
      body: grantInput,
      timeout: 2000,
      fault: { kind: "disconnect" },
    });
    assert.equal(observation.kind, "sdk-error");
  },
);

for (const [id, fault] of [
  ["reuse-after-timeout", { kind: "slow" }],
  ["reuse-after-decoding-error", { kind: "malformed" }],
] as const)
  sdkTest(
    {
      id,
      operation: "getCurrentSession",
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ sequence }) => {
      const healthy: CaseCall = {
        operation: "getCurrentSession",
        headers: { Authorization: "Bearer sdk-human" },
        timeout: 100,
      };
      const [failed, reused] = await sequence([{ ...healthy, fault }, healthy]);
      assert.equal(failed!.observation.kind, "sdk-error");
      assert.equal(
        assertSuccess(reused!.observation, 200).principalId,
        "00000000-0000-4000-8000-000000000001",
      );
    },
  );

for (const [id, status, contentType, bytes] of [
  ["required-response-null", 200, "application/json", "null"],
  ["required-response-empty", 200, "application/json", ""],
  ["undeclared-bodyless-success", 204, "application/json", ""],
  [
    "undeclared-created-success",
    201,
    "application/json",
    '{"principalId":"00000000-0000-4000-8000-000000000001"}',
  ],
  ["incompatible-response-type", 200, "text/plain; charset=utf-8", "not-json"],
] as const) {
  sdkTest(
    { id, operation: "getCurrentSession", outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation: "getCurrentSession",
        headers: {},
        timeout: 2000,
        fault: {
          kind: "raw",
          status,
          contentType,
          bodyBase64: Buffer.from(bytes).toString("base64"),
        },
      });
      assert.equal(observation.kind, "sdk-error", JSON.stringify(observation));
      assert.equal(observation.status, status);
      assert.equal(rawText(observation.raw), bytes);
    },
  );
}

sdkTest(
  {
    id: "nullable-response",
    operation: "contractFixtureNullable",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureNullable",
      headers: {},
      timeout: 2000,
    });
    assert.equal(observation.kind, "success", JSON.stringify(observation));
    assert.equal(observation.status, 200);
    assert.equal(observation.body, null);
    assert.ok(Object.hasOwn(observation, "body"));
    assert.ok(
      ["generated-model", "generated-schema"].includes(observation.validation),
    );
  },
);

sdkTest(
  {
    id: "bodyless-response",
    operation: "contractFixtureEmpty",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureEmpty",
      headers: {},
      timeout: 2000,
    });
    assert.equal(observation.kind, "success", JSON.stringify(observation));
    assert.equal(observation.status, 204);
    assert.equal(Object.hasOwn(observation, "body"), false);
    assert.equal(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "raw-bytes-and-repeated-headers",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call, profile }) => {
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 2000,
      fault: {
        kind: "raw",
        status: 200,
        contentType: "application/json",
        bodyBase64: "/wA=",
        headers: [
          ["www-authenticate", "Bearer realm=first"],
          ["www-authenticate", "Bearer realm=second"],
          ["set-cookie", "first=one"],
          ["set-cookie", "second=two"],
        ],
      },
    });
    assert.equal(observation.kind, "sdk-error");
    const values = headerValues(observation, "www-authenticate").join(", ");
    assert.match(values, /realm=first/);
    assert.match(values, /realm=second/);
    if (profile.startsWith("typescript"))
      assert.equal(rawText(observation.raw), "\uFFFD\0");
    else
      assert.deepEqual(observation.raw, { encoding: "base64", value: "/wA=" });
    if (profile === "typescript-chromium")
      assert.deepEqual(headerValues(observation, "set-cookie"), []);
    else if (profile.startsWith("python") || profile === "rust")
      assert.deepEqual(headerValues(observation, "set-cookie"), [
        "first=one",
        "second=two",
      ]);
  },
);

sdkTest(
  {
    id: "invalid-primitive-response",
    operation: "getHealth",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getHealth",
      headers: {},
      timeout: 2000,
      fault: { kind: "json", body: { status: 123 } },
    });
    assert.equal(observation.kind, "sdk-error", JSON.stringify(observation));
    assert.equal(observation.status, 200);
  },
);

for (const contentType of [
  "application/json",
  "application/json; charset=iso-8859-1",
]) {
  sdkTest(
    {
      id: contentType.includes("charset")
        ? "invalid-json-utf8-charset"
        : "invalid-json-utf8",
      operation: "getHealth",
      outcome: "failure",
    },
    async ({ call }) => {
      const bytes = Buffer.concat([
        Buffer.from('{"status":"'),
        Buffer.from([255]),
        Buffer.from('"}'),
      ]);
      const { observation } = await call({
        operation: "getHealth",
        headers: {},
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 200,
          contentType,
          bodyBase64: bytes.toString("base64"),
        },
      });
      assert.equal(observation.kind, "sdk-error", JSON.stringify(observation));
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );
}

sdkTest(
  {
    id: "undeclared-error-raw-bytes",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call, profile }) => {
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 2000,
      fault: {
        kind: "raw",
        status: 418,
        contentType: "application/octet-stream",
        bodyBase64: "/wA=",
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 418);
    if (profile.startsWith("typescript"))
      assert.equal(rawText(observation.raw), "\uFFFD\0");
    else
      assert.deepEqual(observation.raw, { encoding: "base64", value: "/wA=" });
  },
);

sdkTest(
  {
    id: "invalid-error-json-utf8",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call, profile }) => {
    const bytes = Buffer.concat([
      Buffer.from(
        '{"type":"about:blank","title":"Authentication required","status":401,"code":"authentication_required","requestId":"00000000-0000-4000-8000-000000000099","detail":"',
      ),
      Buffer.from([255]),
      Buffer.from('"}'),
    ]);
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 2000,
      fault: {
        kind: "raw",
        status: 401,
        contentType: "application/problem+json",
        bodyBase64: bytes.toString("base64"),
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 401);
    assert.notEqual(
      observation.validation,
      "generated-model",
      "Invalid bytes cannot become a generated Problem Details model",
    );
    if (profile === "rust" || profile.startsWith("python"))
      assert.deepEqual(observation.raw, {
        encoding: "base64",
        value: bytes.toString("base64"),
      });
  },
);
