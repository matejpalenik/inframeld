import assert from "node:assert/strict";
import test from "node:test";
import {
  assertSuccess,
  assertJsonBody,
  assertDispatch,
} from "../../src/conformance/assertions.ts";
import type { Observation } from "../../src/conformance/protocol.ts";

test("an uncertain write cannot hide redispatch or a different operation", () => {
  const expected = { method: "POST", path: "/grants", count: 1 };
  assertDispatch(expected, "POST", "/grants");
  for (const wrong of [
    { ...expected, count: 2 },
    { ...expected, method: "GET" },
    { ...expected, path: "/other" },
  ])
    assert.throws(() => assertDispatch(wrong, "POST", "/grants"));
});

test("HTTP 200 alone cannot turn a native decoding failure into success", () => {
  assert.throws(() =>
    assertSuccess(
      {
        kind: "sdk-error",
        callId: "bad",
        status: 200,
        body: { status: "ok" },
        validation: "none",
        headers: [],
        error: "Cannot decode",
      },
      200,
    ),
  );
});

test("a well-shaped grant body cannot conceal an incorrect HTTP status", () => {
  const observation: Observation = {
    kind: "success",
    callId: "grant",
    status: 200,
    body: { canGrant: false },
    validation: "generated-model",
    headers: [],
  };
  assert.throws(() => assertSuccess(observation, 201), /status/);
  assert.deepEqual(assertSuccess({ ...observation, status: 201 }, 201), {
    canGrant: false,
  });
});
test("consent input mutations cannot pass the independent wire assertion", () => {
  const body = { consentChallenge: "a+b&/", decision: "allow", remember: true };
  assertJsonBody({ jsonBody: body }, body);
  for (const wrong of [
    { ...body, decision: "deny" },
    { ...body, remember: false },
  ])
    assert.throws(
      () => assertJsonBody({ jsonBody: wrong }, body),
      /different JSON body/,
    );
});
