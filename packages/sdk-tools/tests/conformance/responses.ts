import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const ready = { value: "ready" };
const accepted = { jobId: "job-123" };
const vendor = "application/vnd.inframeld.job+json";

for (const [mode, status, expected] of [
  ["ready", 200, ready],
  ["accepted", 202, accepted],
  ["fallback", 201, accepted],
] as const) {
  sdkTest(
    {
      id: `response-${mode}`,
      operation: "contractFixtureVariants",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "contractFixtureVariants",
        headers: {},
        query: { mode },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, status), expected);
      assert.equal(
        new URLSearchParams(String(witness.query)).get("mode"),
        mode,
      );
    },
  );
  sdkTest(
    {
      id: `response-${mode}-wrong-body`,
      operation: "contractFixtureVariants",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureVariants",
        headers: {},
        query: { mode },
        timeout: 2000,
        fault: {
          kind: "json",
          status,
          body: status === 200 ? accepted : ready,
        },
      });
      assert.equal(
        observation.kind,
        "sdk-error",
        "A schema for another status must not validate this response",
      );
      assert.equal(observation.status, status);
      assert.ok(observation.raw);
    },
  );
}

for (const [name, mediaType, expected] of [
  ["json", "application/json", ready],
  ["vendor", vendor, accepted],
] as const) {
  sdkTest(
    {
      id: `representation-${name}`,
      operation: "contractFixtureMedia",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "contractFixtureMedia",
        headers: { Accept: mediaType },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), expected);
      assert.deepEqual(headerValues(observation, "content-type"), [mediaType]);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers.accept, mediaType);
    },
  );
  sdkTest(
    {
      id: `representation-${name}-parameters`,
      operation: "contractFixtureMedia",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureMedia",
        headers: { Accept: mediaType },
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 200,
          bodyBase64: Buffer.from(JSON.stringify(expected)).toString("base64"),
          contentType: mediaType.toUpperCase() + "; charset=utf-8",
        },
      });
      assert.deepEqual(assertSuccess(observation, 200), expected);
    },
  );
  sdkTest(
    {
      id: `representation-${name}-wrong-body`,
      operation: "contractFixtureMedia",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureMedia",
        headers: { Accept: mediaType },
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 200,
          bodyBase64: Buffer.from(
            JSON.stringify(name === "json" ? accepted : ready),
          ).toString("base64"),
          contentType: mediaType,
        },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );
}

for (const [name, contentType] of [
  ["missing", null],
  ["incompatible", "text/plain"],
] as const)
  sdkTest(
    {
      id: `representation-${name}`,
      operation: "contractFixtureMedia",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureMedia",
        headers: {},
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 200,
          bodyBase64: Buffer.from(JSON.stringify(ready)).toString("base64"),
          contentType,
        },
      });
      assert.equal(
        observation.kind,
        "sdk-error",
        "An ambiguous or incompatible representation must remain a failure",
      );
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );

sdkTest(
  {
    id: "response-mixed-empty",
    operation: "contractFixtureVariants",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureVariants",
      headers: {},
      query: { mode: "empty" },
      timeout: 2000,
    });
    assert.equal(observation.kind, "success", JSON.stringify(observation));
    assert.equal(observation.status, 204);
    assert.equal(observation.validation, "none");
    assert.equal(Object.hasOwn(observation, "body"), false);
  },
);
sdkTest(
  {
    id: "representation-secondary-null",
    operation: "contractFixtureMedia",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureMedia",
      headers: { Accept: vendor },
      timeout: 2000,
      fault: {
        kind: "raw",
        status: 200,
        bodyBase64: Buffer.from("null").toString("base64"),
        contentType: vendor,
      },
    });
    assert.equal(observation.kind, "success", JSON.stringify(observation));
    assert.equal(observation.status, 200);
    assert.equal(observation.body, null);
    assert.ok(
      ["generated-model", "generated-schema"].includes(observation.validation),
    );
  },
);

for (const [name, status, mediaType, body] of [
  ["ready", 201, "application/json", ready],
  ["vendor", 202, vendor, accepted],
  ["nullable", 202, vendor, null],
] as const) {
  sdkTest(
    {
      id: `fallback-${name}`,
      operation: "contractFixtureFallback",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureFallback",
        headers: { Accept: mediaType },
        query: { mode: name },
        timeout: 2000,
      });
      assert.equal(observation.kind, "success", JSON.stringify(observation));
      assert.equal(observation.status, status);
      assert.deepEqual(observation.body, body);
      assert.ok(
        ["generated-model", "generated-schema"].includes(
          observation.validation,
        ),
      );
    },
  );
}
sdkTest(
  {
    id: "fallback-empty",
    operation: "contractFixtureFallback",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureFallback",
      headers: {},
      query: { mode: "empty" },
      timeout: 2000,
    });
    assert.equal(observation.kind, "success", JSON.stringify(observation));
    assert.equal(observation.status, 204);
    assert.equal(Object.hasOwn(observation, "body"), false);
  },
);
for (const [name, mediaType, body] of [
  ["vendor", vendor, accepted],
  ["nullable", vendor, null],
] as const)
  sdkTest(
    {
      id: `fallback-error-${name}`,
      operation: "contractFixtureFallback",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureFallback",
        headers: { Accept: mediaType },
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 401,
          bodyBase64: Buffer.from(JSON.stringify(body)).toString("base64"),
          contentType: mediaType,
        },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 401);
      if (body !== null) assert.deepEqual(observation.body, body);
      assert.equal(
        observation.cause,
        undefined,
        "A valid alternate error representation must not cause a decoding failure",
      );
      assert.ok(observation.raw);
    },
  );

for (const [name, body] of [
  ["empty", ""],
  ["unexpected", JSON.stringify(accepted)],
] as const)
  sdkTest(
    {
      id: `exact-bodyless-error-${name}`,
      operation: "contractFixtureFallback",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "contractFixtureFallback",
        headers: {},
        timeout: 2000,
        fault: {
          kind: "raw",
          status: 404,
          bodyBase64: Buffer.from(body).toString("base64"),
          contentType: vendor,
        },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 404);
      assert.ok(
        !["generated-model", "generated-schema"].includes(
          observation.validation,
        ),
        "Exact bodyless response cannot fall through to a default error schema",
      );
      if (name === "empty") assert.equal(observation.cause, undefined);
    },
  );

sdkTest(
  {
    id: "undeclared-error-provenance",
    operation: "contractFixtureMedia",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "contractFixtureMedia",
      headers: {},
      timeout: 2000,
      fault: {
        kind: "json",
        status: 418,
        body: { message: "unknown response" },
        contentType: "application/json",
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 418);
    assert.ok(
      !["generated-model", "generated-schema"].includes(observation.validation),
      "Unconstrained JSON is not a generated validated error model",
    );
    assert.ok(observation.raw);
  },
);
