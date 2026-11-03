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
const human = {
  principalId: "00000000-0000-4000-8000-000000000001",
  displayName: "SDK Human",
  kind: "human",
};
const items = [
  human,
  {
    principalId: "00000000-0000-4000-8000-000000000005",
    displayName: "Stored application",
    kind: "application",
  },
  {
    principalId: "00000000-0000-4000-8000-000000000006",
    displayName: "Legacy\nmember 🧭",
    kind: "human",
  },
];
const page = { projectId, accessRevision: 12, items, nextCursor: null };

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `project-members-${credential}`,
      operation: "listProjectMembers",
      outcome: "success",
    },
    async ({ call }) => {
      const headers =
        credential === "bearer"
          ? bearer
          : { Cookie: "ory_kratos_session=sdk-cookie" };
      const { observation, witness } = await call({
        operation: "listProjectMembers",
        path,
        headers,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), page);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.equal(witness.query, "");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], undefined);
      assert.equal(witness.csrf, "");
      assert.equal(witness.rawBodyBase64, "");
    },
  );

sdkTest(
  {
    id: "project-members-explicit-continuation",
    operation: "listProjectMembers",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ call }) => {
    const first = await call({
      operation: "listProjectMembers",
      path,
      headers: bearer,
      query: { limit: 1 },
      timeout: 2000,
    });
    const firstBody = assertSuccess(first.observation, 200);
    assert.deepEqual(firstBody.items, items.slice(0, 1));
    assert.equal(firstBody.projectId, projectId);
    assert.equal(firstBody.accessRevision, 12);
    assert.equal(typeof firstBody.nextCursor, "string");
    assert.ok(typeof firstBody.nextCursor === "string");
    assert.deepEqual(
      [...new URLSearchParams(String(first.witness.query))],
      [["limit", "1"]],
    );
    const next = await call({
      operation: "listProjectMembers",
      path,
      headers: bearer,
      query: { limit: 2, cursor: firstBody.nextCursor },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(next.observation, 200), {
      ...page,
      items: items.slice(1),
    });
    const query = new URLSearchParams(String(next.witness.query));
    assert.deepEqual(query.getAll("limit"), ["2"]);
    assert.deepEqual(query.getAll("cursor"), [firstBody.nextCursor]);
    assert.equal([...query].length, 2);
  },
);

sdkTest(
  {
    id: "project-members-empty-page",
    operation: "listProjectMembers",
    outcome: "success",
  },
  async ({ call }) => {
    const empty = { ...page, accessRevision: 19, items: [] };
    const { observation } = await call({
      operation: "listProjectMembers",
      path,
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
  project?: string;
  cursor?: string;
}[] = [
  {
    id: "unauthenticated",
    headers: {},
    status: 401,
    code: "http_error",
  },
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
      id: `project-members-${failure.id}`,
      operation: "listProjectMembers",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "listProjectMembers",
        path: { project_id: failure.project ?? projectId },
        headers: failure.headers,
        query: failure.cursor ? { cursor: failure.cursor } : undefined,
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

for (const [id, body] of [
  ["missing-next-cursor", { projectId, accessRevision: 12, items }],
  ["null-items", { ...page, items: null }],
  ["invalid-kind", { ...page, items: [{ ...human, kind: "operator" }] }],
  ["invalid-principal", { ...page, items: [{ ...human, principalId: 42 }] }],
] satisfies [string, JsonValue][])
  sdkTest(
    {
      id: `project-members-${id}`,
      operation: "listProjectMembers",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "listProjectMembers",
        path,
        headers: bearer,
        timeout: 2000,
        fault: { kind: "json", status: 200, body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );
