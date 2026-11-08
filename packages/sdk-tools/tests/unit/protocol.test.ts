import assert from "node:assert/strict";
import test from "node:test";
import {
  parseDriverReply,
  driverRequestSchema,
  type DriverRequest,
} from "../../src/conformance/protocol.ts";

test("application identity accepts a header-only call without body/query/retry input", () => {
  const request = {
    version: 2,
    profile: "typescript-node",
    caseId: "application-session",
    baseUrl: "http://localhost/",
    calls: [
      {
        id: "identity",
        operation: "getCurrentApplicationSession",
        headers: { Authorization: "Bearer synthetic-input" },
        timeout: 100,
      },
    ],
  };
  assert.deepEqual(driverRequestSchema.parse(request), request);
});

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

test("invitation envelopes preserve preview key absence and each write's exact key", () => {
  const body = { invitationToken: "A".repeat(43) };
  const calls = [
    {
      id: "issue",
      operation: "issueInvitation",
      headers: { "Idempotency-Key": "issue-original" },
      body: {
        organizationId: "00000000-0000-4000-8000-000000000002",
        expectedAccessRevision: 7,
        assignments: [{ kind: "admission-only" }],
        expectedProjectAccessRevisions: [],
      },
      timeout: 100,
    },
    {
      id: "revoke",
      operation: "revokeInvitation",
      path: { invitation_id: "00000000-0000-4000-8000-000000000006" },
      headers: { "Idempotency-Key": "revoke-original" },
      body: { expectedAccessRevision: 7 },
      timeout: 100,
    },
    {
      id: "preview",
      operation: "previewInvitation",
      headers: {},
      body,
      timeout: 100,
    },
    {
      id: "activate",
      operation: "activateInvitation",
      headers: { "Idempotency-Key": "activate-original" },
      body,
      timeout: 100,
    },
  ];
  const input = { ...request, calls };
  assert.deepEqual(driverRequestSchema.parse(input), input);
});
