import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const path = { project_id: projectId };
const bearer = { Authorization: "Bearer sdk-human" };
const actionId = "inspect-budget";
const delegatingGrant = {
  projectId,
  recipientPrincipalId: "00000000-0000-4000-8000-000000000001",
  actionId,
  canGrant: true,
};
const items = [
  delegatingGrant,
  {
    projectId,
    recipientPrincipalId: "00000000-0000-4000-8000-000000000006",
    actionId,
    canGrant: false,
  },
];
const page = { items, nextCursor: null };

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `project-action-grants-${credential}`,
      operation: "listProjectActionGrants",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "listProjectActionGrants",
        path,
        query: { actionId },
        headers:
          credential === "bearer"
            ? bearer
            : { Cookie: "ory_kratos_session=sdk-cookie" },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), page);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.equal(witness.method, "GET");
      assert.equal(witness.path, `/v1/projects/${projectId}/grants`);
      assert.deepEqual(
        [...new URLSearchParams(String(witness.query))],
        [["actionId", actionId]],
      );
      assert.equal(witness.rawBodyBase64, "");
      assert.equal(witness.csrf, "");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], undefined);
    },
  );

sdkTest(
  {
    id: "project-action-grants-explicit-continuation",
    operation: "listProjectActionGrants",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ call }) => {
    const first = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId, limit: 1 },
      headers: bearer,
      timeout: 2000,
    });
    const body = assertSuccess(first.observation, 200);
    assert.deepEqual(body.items, items.slice(0, 1));
    assert.equal(typeof body.nextCursor, "string");
    assert.ok(typeof body.nextCursor === "string");
    assert.deepEqual(
      [...new URLSearchParams(String(first.witness.query))],
      [
        ["actionId", actionId],
        ["limit", "1"],
      ],
    );
    const next = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId, limit: 2, cursor: body.nextCursor },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(next.observation, 200), {
      items: items.slice(1),
      nextCursor: null,
    });
    const query = new URLSearchParams(String(next.witness.query));
    assert.deepEqual(query.getAll("actionId"), [actionId]);
    assert.deepEqual(query.getAll("limit"), ["2"]);
    assert.deepEqual(query.getAll("cursor"), [body.nextCursor]);
    assert.equal([...query].length, 3);
    assert.equal(next.witness.rawBodyBase64, "");
  },
);

sdkTest(
  {
    id: "project-action-grants-current-auth-on-continuation",
    operation: "listProjectActionGrants",
    outcome: "failure",
    expectedCalls: 2,
  },
  async ({ call }) => {
    const first = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId, limit: 1 },
      headers: bearer,
      timeout: 2000,
    });
    const cursor = assertSuccess(first.observation, 200).nextCursor;
    assert.ok(typeof cursor === "string");
    const denied = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId, cursor },
      headers: { Authorization: "Bearer sdk-denied" },
      timeout: 2000,
    });
    assert.equal(denied.observation.kind, "sdk-error");
    assert.equal(denied.observation.status, 403);
    assert.ok(
      denied.observation.body &&
        typeof denied.observation.body === "object" &&
        !Array.isArray(denied.observation.body),
    );
    assert.equal(denied.observation.body.code, "access_denied");
    assert.deepEqual(headerValues(denied.observation, "cache-control"), [
      "no-store",
    ]);
  },
);

sdkTest(
  {
    id: "project-action-grants-cursor-cannot-cross-action",
    operation: "listProjectActionGrants",
    outcome: "failure",
    expectedCalls: 2,
  },
  async ({ call }) => {
    const first = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId, limit: 1 },
      headers: bearer,
      timeout: 2000,
    });
    const cursor = assertSuccess(first.observation, 200).nextCursor;
    assert.ok(typeof cursor === "string");
    const next = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId: "manage-budget", cursor },
      headers: bearer,
      timeout: 2000,
    });
    assert.equal(next.observation.kind, "sdk-error");
    assert.equal(next.observation.status, 422);
    assert.ok(
      next.observation.body &&
        typeof next.observation.body === "object" &&
        !Array.isArray(next.observation.body),
    );
    assert.equal(next.observation.body.code, "invalid_input");
    assert.equal(
      new URLSearchParams(String(next.witness.query)).get("actionId"),
      "manage-budget",
    );
  },
);

sdkTest(
  {
    id: "project-action-grants-empty-page",
    operation: "listProjectActionGrants",
    outcome: "success",
  },
  async ({ call }) => {
    const empty = { items: [], nextCursor: null };
    const { observation } = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId },
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: empty },
    });
    assert.deepEqual(assertSuccess(observation, 200), empty);
  },
);

const failures: {
  id: string;
  headers: Record<string, string>;
  status: number;
  code: string;
  action?: string;
  project?: string;
  cursor?: string;
}[] = [
  { id: "unauthenticated", headers: {}, status: 401, code: "http_error" },
  {
    id: "application-key-denied",
    headers: { Authorization: "Bearer ifm_app_unsupported" },
    status: 401,
    code: "http_error",
  },
  {
    id: "forbidden",
    headers: { Authorization: "Bearer sdk-denied" },
    status: 403,
    code: "access_denied",
  },
  {
    id: "use-only-cannot-inspect",
    headers: bearer,
    status: 403,
    code: "access_denied",
    action: "inspect-feedback",
  },
  {
    id: "hidden-project",
    headers: bearer,
    status: 404,
    code: "resource_not_found",
    project: "00000000-0000-4000-8000-000000000099",
  },
  {
    id: "unavailable",
    headers: { Authorization: "Bearer sdk-unavailable" },
    status: 503,
    code: "dependency_unavailable",
  },
  {
    id: "invalid-cursor",
    headers: bearer,
    status: 422,
    code: "invalid_input",
    cursor: "malformed_cursor",
  },
];
for (const failure of failures)
  sdkTest(
    {
      id: `project-action-grants-${failure.id}`,
      operation: "listProjectActionGrants",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "listProjectActionGrants",
        path: { project_id: failure.project ?? projectId },
        query: {
          actionId: failure.action ?? actionId,
          ...(failure.cursor ? { cursor: failure.cursor } : {}),
        },
        headers: failure.headers,
        timeout: 2000,
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
      assert.equal(typeof observation.body.requestId, "string");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      if (failure.status === 401)
        assert.ok(
          headerValues(observation, "www-authenticate")[0]?.startsWith(
            "Bearer ",
          ),
        );
    },
  );

sdkTest(
  {
    id: "project-action-grants-encoded-unsupported-action",
    operation: "listProjectActionGrants",
    outcome: "failure",
  },
  async ({ call }) => {
    const encodedAction = "inspect-budget+&/:";
    const { observation, witness } = await call({
      operation: "listProjectActionGrants",
      path,
      query: { actionId: encodedAction },
      headers: bearer,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 422);
    assert.ok(
      observation.body &&
        typeof observation.body === "object" &&
        !Array.isArray(observation.body),
    );
    assert.equal(observation.body.code, "invalid_input");
    assert.deepEqual(
      [...new URLSearchParams(String(witness.query))],
      [["actionId", encodedAction]],
    );
    assert.equal(witness.rawBodyBase64, "");
  },
);

for (const [id, body] of [
  ["missing-next-cursor", { items }],
  ["null-items", { ...page, items: null }],
  [
    "invalid-recipient",
    { ...page, items: [{ ...delegatingGrant, recipientPrincipalId: 42 }] },
  ],
  [
    "invalid-grant-level",
    { ...page, items: [{ ...delegatingGrant, canGrant: "false" }] },
  ],
  ["invalid-next-cursor", { ...page, nextCursor: 42 }],
] satisfies [string, JsonValue][])
  sdkTest(
    {
      id: `project-action-grants-${id}`,
      operation: "listProjectActionGrants",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "listProjectActionGrants",
        path,
        query: { actionId },
        headers: bearer,
        timeout: 2000,
        fault: { kind: "json", status: 200, body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );
