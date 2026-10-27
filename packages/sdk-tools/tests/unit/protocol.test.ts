import assert from "node:assert/strict";
import test from "node:test";
import {
  parseDriverReply,
  type DriverRequest,
} from "../../src/conformance/protocol.ts";

const request: DriverRequest = {
  version: 2,
  profile: "rust",
  caseId: "health",
  baseUrl: "http://127.0.0.1",
  calls: [{ id: "one", operation: "getHealth", headers: {}, timeout: 1000 }],
};
const observation = {
  kind: "success",
  callId: "one",
  validation: "generated-model",
  headers: [],
  status: 200,
  body: { status: "ok" },
};
const reply = {
  version: 2,
  profile: "rust",
  caseId: "health",
  kind: "observations",
  observations: [observation],
};

test("protocol v2 records validation provenance and preserves null versus absence", () => {
  const input = { ...request, version: 2 as const };
  const entry = {
    kind: "success",
    callId: "one",
    validation: "generated-schema",
    headers: [],
    status: 200,
    body: null,
  };
  const parsed = parseDriverReply(input, {
    ...reply,
    version: 2,
    observations: [entry],
  });
  assert.equal(parsed[0]?.body, null);
  assert.ok(Object.hasOwn(parsed[0]!, "body"));
  const { body: _body, ...absent } = entry;
  assert.ok(
    !Object.hasOwn(
      parseDriverReply(input, {
        ...reply,
        version: 2,
        observations: [absent],
      })[0]!,
      "body",
    ),
  );
});

test("native success is accepted only with a complete matching result inventory", () => {
  assert.equal(parseDriverReply(request, reply).length, 1);
  for (const observations of [
    [],
    [observation, observation],
    [{ ...observation, callId: "other" }],
  ]) {
    assert.throws(
      () => parseDriverReply(request, { ...reply, observations }),
      /inventory/i,
    );
  }
});
test("wrong protocol, profile, identity, contradictory success and driver errors fail visibly", () => {
  for (const value of [
    { ...reply, version: 1 },
    { ...reply, profile: "python-sync" },
    { ...reply, caseId: "other" },
    { ...reply, observations: [{ ...observation, error: "decode failed" }] },
  ])
    assert.throws(() => parseDriverReply(request, value));
  assert.throws(
    () =>
      parseDriverReply(request, {
        version: 2,
        profile: "rust",
        caseId: "health",
        kind: "driver-error",
        error: "operation missing",
      }),
    /operation missing/,
  );
});
