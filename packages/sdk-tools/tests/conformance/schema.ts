import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  assertJsonBody,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { grantInput, grantResponse, projectId } from "./grants.ts";

export const payload = {
  required_name: "valid",
  required_nullable: null,
  score: 0.5,
  choice: 7,
};

sdkTest(
  {
    id: "problem-path-union",
    operation: "contractFixturePayload",
    outcome: "failure",
  },
  async ({ call }) => {
    const problem = {
      type: "https://problems.test/future",
      title: "Future",
      status: 422,
      detail: "A future error",
      code: "future_error_code",
      requestId: "00000000-0000-4000-8000-000000000099",
      errors: [
        {
          location: "body",
          path: ["items", 0],
          code: "out_of_range",
          message: "Out of range",
        },
      ],
    };
    const { observation } = await call({
      operation: "contractFixturePayload",
      headers: {},
      body: payload,
      timeout: 2000,
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
  },
);

for (const [id, body] of [
  ["payload-integer", payload],
  ["payload-string", { ...payload, choice: "seven" }],
  ["optional-absent", payload],
  ["optional-null", { ...payload, optional_nullable: null }],
  ["optional-value", { ...payload, optional_nullable: "reviewed" }],
] as const)
  sdkTest(
    { id, operation: "contractFixturePayload", outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "contractFixturePayload",
        headers: {},
        body,
        timeout: 2000,
      });
      const returned = assertSuccess(observation, 200);
      assert.equal(returned.choice, body.choice);
      assert.equal(returned.required_nullable, null);
      assertJsonBody(witness, body);
    },
  );

for (const [id, canGrant] of [
  ["constant-rejects-true", true],
  ["nonnull-rejects-null", null],
] as const)
  sdkTest(
    { id, operation: "assignProjectUseOnlyGrant", outcome: "failure" },
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
        fault: {
          kind: "json",
          status: 201,
          body: { ...grantResponse, canGrant },
        },
      });
      assert.equal(
        observation.kind,
        "sdk-error",
        "Malformed HTTP 201 must not be a typed success",
      );
      assert.equal(observation.status, 201);
      assert.deepEqual(headerValues(observation, "x-request-id"), [
        "00000000-0000-4000-8000-000000000099",
      ]);
      assert.ok(
        observation.raw,
        "Decoding failure must retain the received body",
      );
    },
  );

sdkTest(
  {
    id: "required-nullable-missing",
    operation: "contractFixturePayload",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixturePayload",
      headers: {},
      body: payload,
      timeout: 2000,
      fault: {
        kind: "json",
        body: { required_name: "valid", score: 0.5, choice: 7 },
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
    assert.ok(observation.raw);
  },
);

sdkTest(
  { id: "page-default", operation: "contractFixturePage", outcome: "success" },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "contractFixturePage",
      headers: {},
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [25],
      nextCursor: null,
    });
    assert.equal(witness.query, "");
  },
);
sdkTest(
  { id: "page-explicit", operation: "contractFixturePage", outcome: "success" },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "contractFixturePage",
      headers: {},
      query: { limit: 7, cursor: "c2RrLWN1cnNvcg" },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [7],
      nextCursor: null,
    });
    assert.equal(new URLSearchParams(String(witness.query)).get("limit"), "7");
    assert.equal(witness.cursor, "c2RrLWN1cnNvcg");
  },
);
sdkTest(
  { id: "upload", operation: "contractFixtureUpload", outcome: "success" },
  async ({ call }) => {
    const body = {
      fileBase64: "AHNkay1iaW5hcnn/",
      fileName: "sdk-upload.bin",
      label: "sdk-label",
    };
    const { observation, witness } = await call({
      operation: "contractFixtureUpload",
      headers: {},
      body,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      filename: body.fileName,
      label: body.label,
    });
    assert.equal(witness.fileBase64, body.fileBase64);
    assert.equal(witness.fileName, body.fileName);
    assert.equal(witness.label, body.label);
  },
);

sdkTest(
  {
    id: "malformed-problem-array",
    operation: "getCurrentSession",
    outcome: "failure",
  },
  async ({ call }) => {
    const problem = {
      type: "about:blank",
      title: "Authentication required",
      status: 401,
      detail: "Sign in",
      code: "authentication_required",
      requestId: "00000000-0000-4000-8000-000000000099",
      errors: {},
    };
    const { observation } = await call({
      operation: "getCurrentSession",
      headers: {},
      timeout: 2000,
      fault: {
        kind: "json",
        status: 401,
        body: problem,
        contentType: "application/problem+json",
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 401);
    assert.equal(
      observation.validation,
      "none",
      "Malformed error arrays cannot become validated API models",
    );
    assert.ok(observation.raw);
    assert.ok(observation.cause);
  },
);
