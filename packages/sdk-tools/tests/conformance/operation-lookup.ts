import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const operation = "lookupOriginalOperation";
const bearer = { Authorization: "Bearer sdk-human" };
const input = {
  installationId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  projectId: "00000000-0000-4000-8000-000000000003",
  method: "POST",
  requestedRoute: "/v1/projects/{project_id}/grants",
  key: "completed +/&é",
  expectedAuthority: {
    family: "project_grant_read",
    actionId: "create-access-groups",
  },
};
const identity = { operationId: "sdk-original-operation" };
const completed = {
  ...identity,
  outcome: "completed_synchronous",
  classification: "safe_result",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
};
const accepted = {
  ...identity,
  outcome: "accepted_asynchronous",
  admission: "confirmed",
  jobReference: "unknown",
  dispatch: "not_established",
  idempotencyExpiresAt: null,
};

for (const [id, key, expected] of [
  ["completed", input.key, completed],
  [
    "issued-secret",
    "issued-secret",
    { ...completed, classification: "issued_secret" },
  ],
  [
    "answer-receipt",
    "answer-receipt",
    { ...completed, classification: "answer_receipt" },
  ],
  ["accepted", "accepted", accepted],
  ["in-progress", "in-progress", { ...identity, outcome: "in_progress" }],
  [
    "recovery-required",
    "recovery-required",
    {
      ...identity,
      outcome: "recovery_required",
      reason: "original_outcome_requires_recovery",
    },
  ],
  ["absent", "absent", { outcome: "unresolved" }],
] as const) {
  sdkTest(
    { id: `lookup-${id}`, operation, outcome: "success" },
    async ({ call }) => {
      const body = { ...input, key };
      const { observation, witness } = await call({
        operation,
        headers: bearer,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), expected);
      assertJsonBody(witness, body);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.deepEqual(headerValues(observation, "location"), []);
    },
  );
}

sdkTest(
  { id: "lookup-cookie", operation, outcome: "success" },
  async ({ call, origin }) => {
    const { observation, witness } = await call({
      operation,
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        Origin: origin,
        "X-Inframeld-CSRF": "1",
      },
      body: input,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), completed);
    assertJsonBody(witness, input);
    assert.equal(witness.origin, origin);
    assert.equal(witness.csrf, "1");
  },
);

for (const [id, scope] of [
  [
    "project-use",
    {
      projectId: input.projectId,
      requestedRoute: "/v1/original-project-operation",
      expectedAuthority: {
        family: "project_action_use",
        actionId: "create-access-groups",
      },
    },
  ],
  [
    "organization-use",
    {
      projectId: null,
      requestedRoute: "/v1/original-organization-operation",
      expectedAuthority: {
        family: "organization_action_use",
        actionId: "create-projects",
      },
    },
  ],
] as const) {
  sdkTest(
    { id: `lookup-${id}`, operation, outcome: "success" },
    async ({ call }) => {
      const body = { ...input, ...scope };
      const { observation, witness } = await call({
        operation,
        headers: bearer,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), completed);
      assertJsonBody(witness, body);
    },
  );
}

sdkTest(
  { id: "lookup-authorized-guard-mismatch", operation, outcome: "success" },
  async ({ call }) => {
    const body = {
      ...input,
      requestedRoute: "/v1/original-project-operation",
      expectedAuthority: {
        family: "project_action_use",
        actionId: "create-pipelines",
      },
    };
    const { observation, witness } = await call({
      operation,
      headers: bearer,
      body,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      outcome: "unresolved",
    });
    assertJsonBody(witness, body);
  },
);

for (const [id, headers, status] of [
  ["missing-credential", {}, 401],
  ["csrf-denied", { Cookie: "ory_kratos_session=sdk-cookie" }, 403],
  ["denied", { Authorization: "Bearer sdk-denied" }, 403],
  ["unavailable", { Authorization: "Bearer sdk-unavailable" }, 503],
  [
    "competing-credentials",
    { ...bearer, Cookie: "ory_kratos_session=sdk-cookie" },
    400,
  ],
] as const) {
  sdkTest(
    { id: `lookup-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers,
        body: input,
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
    },
  );
}

for (const [id, guard] of [
  [
    "fixed-grant-downgrade",
    { family: "project_action_use", actionId: "create-access-groups" },
  ],
  [
    "wrong-fixed-action",
    { family: "project_grant_read", actionId: "create-pipelines" },
  ],
  [
    "organization-project-mismatch",
    { family: "organization_action_use", actionId: "create-projects" },
  ],
] as const) {
  sdkTest(
    { id: `lookup-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const body = { ...input, expectedAuthority: guard };
      const { observation, witness } = await call({
        operation,
        headers: bearer,
        body,
        timeout: 2000,
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 422);
      assert.notEqual(observation.validation, "none");
      assertJsonBody(witness, body);
    },
  );
}

for (const [id, body] of [
  ["unknown-outcome", { outcome: "finished", ...identity }],
  [
    "missing-outcome",
    {
      ...identity,
      classification: "safe_result",
      idempotencyExpiresAt: completed.idempotencyExpiresAt,
    },
  ],
  [
    "missing-job-reference",
    {
      ...identity,
      outcome: "accepted_asynchronous",
      admission: "confirmed",
      dispatch: "not_established",
      idempotencyExpiresAt: null,
    },
  ],
  ["claimed-known-reference", { ...accepted, jobReference: "known" }],
] as const) {
  sdkTest(
    { id: `lookup-rejects-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers: bearer,
        body: input,
        timeout: 2000,
        fault: { kind: "json", body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
      assert.ok(observation.raw);
    },
  );
}

for (const [id, fault] of [
  ["timeout", { kind: "slow" }],
  ["disconnect", { kind: "disconnect" }],
] as const) {
  sdkTest(
    { id: `lookup-${id}`, operation, outcome: "failure" },
    async ({ call }) => {
      const { observation } = await call({
        operation,
        headers: bearer,
        body: input,
        timeout: id === "timeout" ? 100 : 2000,
        fault,
      });
      assert.equal(observation.kind, "sdk-error");
    },
  );
}
