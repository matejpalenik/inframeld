import assert from "node:assert/strict";
import { sdkTest, type CaseCall } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertJsonBody,
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

const principalId = "00000000-0000-4000-8000-000000000001";
const groupId = "00000000-0000-4000-8000-000000000007";
const applicationId = "00000000-0000-4000-8000-000000000008";
const ownGrants: JsonValue[] = [
  {
    target: { kind: "project", projectId },
    actionId,
    canGrant: true,
  },
  {
    target: { kind: "access-group", projectId, accessGroupId: groupId },
    actionId: "add-documents",
    canGrant: false,
  },
  {
    target: {
      kind: "application-account",
      projectId,
      applicationPrincipalId: applicationId,
    },
    actionId: "issue-application-keys",
    canGrant: true,
  },
];
const ownPage = {
  projectId,
  principalId,
  accessRevision: 7,
  grants: ownGrants,
  groupMemberships: [{ accessGroupId: groupId }],
  groupManagements: [{ accessGroupId: groupId }],
  nextCursor: null,
};

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `my-project-access-${credential}`,
      operation: "getMyProjectAccess",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "getMyProjectAccess",
        path,
        headers:
          credential === "bearer"
            ? bearer
            : { Cookie: "ory_kratos_session=sdk-cookie" },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), ownPage);
      assertDispatch(witness, "GET", `/v1/projects/${projectId}/my-access`);
      assert.equal(witness.query, "");
      assert.equal(witness.rawBodyBase64, "");
      assert.equal(witness.csrf, "");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

sdkTest(
  {
    id: "my-project-access-combined-continuation",
    operation: "getMyProjectAccess",
    outcome: "success",
    expectedCalls: 3,
  },
  async ({ call }) => {
    const first = await call({
      operation: "getMyProjectAccess",
      path,
      query: { limit: 2 },
      headers: bearer,
      timeout: 2000,
    });
    const firstBody = assertSuccess(first.observation, 200);
    assert.ok(typeof firstBody.nextCursor === "string");
    assert.deepEqual(firstBody, {
      ...ownPage,
      grants: ownGrants.slice(0, 2),
      groupMemberships: [],
      groupManagements: [],
      nextCursor: firstBody.nextCursor,
    });
    const second = await call({
      operation: "getMyProjectAccess",
      path,
      query: { limit: 2, cursor: firstBody.nextCursor },
      headers: bearer,
      timeout: 2000,
    });
    const secondBody = assertSuccess(second.observation, 200);
    assert.ok(typeof secondBody.nextCursor === "string");
    assert.deepEqual(secondBody, {
      ...ownPage,
      grants: ownGrants.slice(2),
      groupManagements: [],
      nextCursor: secondBody.nextCursor,
    });
    const third = await call({
      operation: "getMyProjectAccess",
      path,
      query: { limit: 2, cursor: secondBody.nextCursor },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(third.observation, 200), {
      ...ownPage,
      grants: [],
      groupMemberships: [],
    });
    for (const [result, cursor] of [
      [first, undefined],
      [second, firstBody.nextCursor],
      [third, secondBody.nextCursor],
    ] as const) {
      assertDispatch(
        result.witness,
        "GET",
        `/v1/projects/${projectId}/my-access`,
      );
      assert.deepEqual(
        [...new URLSearchParams(String(result.witness.query))],
        [["limit", "2"], ...(cursor ? [["cursor", cursor]] : [])],
      );
      assert.equal(result.witness.rawBodyBase64, "");
      assert.deepEqual(headerValues(result.observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);

sdkTest(
  {
    id: "my-project-access-current-auth-on-continuation",
    operation: "getMyProjectAccess",
    outcome: "failure",
    expectedCalls: 2,
  },
  async ({ call }) => {
    const first = await call({
      operation: "getMyProjectAccess",
      path,
      query: { limit: 1 },
      headers: bearer,
      timeout: 2000,
    });
    const cursor = assertSuccess(first.observation, 200).nextCursor;
    assert.ok(typeof cursor === "string");
    const denied = await call({
      operation: "getMyProjectAccess",
      path,
      query: { cursor },
      headers: { Authorization: "Bearer sdk-denied" },
      timeout: 2000,
    });
    assert.equal(denied.observation.kind, "sdk-error");
    assert.equal(denied.observation.status, 403);
    assert.notEqual(denied.observation.validation, "none");
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

for (const failure of failures.filter((entry) =>
  [
    "unauthenticated",
    "forbidden",
    "hidden-project",
    "unavailable",
    "invalid-cursor",
  ].includes(entry.id),
))
  sdkTest(
    {
      id: `my-project-access-${failure.id}`,
      operation: "getMyProjectAccess",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation: "getMyProjectAccess",
        path: { project_id: failure.project ?? projectId },
        ...(failure.cursor ? { query: { cursor: failure.cursor } } : {}),
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
      assert.equal(witness.rawBodyBase64, "");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

const { nextCursor: _ownCursor, ...ownWithoutCursor } = ownPage;
for (const [id, body] of [
  ["missing-next-cursor", ownWithoutCursor],
  ["boolean-revision", { ...ownPage, accessRevision: true }],
  [
    "unsupported-target",
    {
      ...ownPage,
      grants: [
        {
          target: { kind: "collection", projectId },
          actionId,
          canGrant: false,
        },
      ],
    },
  ],
] satisfies [string, JsonValue][])
  sdkTest(
    {
      id: `my-project-access-${id}`,
      operation: "getMyProjectAccess",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call({
        operation: "getMyProjectAccess",
        path,
        headers: bearer,
        timeout: 2000,
        fault: { kind: "json", status: 200, body },
      });
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, 200);
    },
  );

const grantRecipient = "00000000-0000-4000-8000-000000000004";
const unchangedGrantRecipient = "00000000-0000-4000-8000-000000000005";
const grantHeaders = { ...bearer, "Idempotency-Key": "sdk-project-grant-key" };
const changes = [
  { kind: "set", operation: "setProjectActionGrant", method: "PUT" },
  { kind: "remove", operation: "removeProjectActionGrant", method: "DELETE" },
] as const;
type GrantChange = (typeof changes)[number]["kind"];

function changeInput(
  kind: GrantChange,
  recipientPrincipalId: string,
  headers: Record<string, string>,
  revision = 7,
  canGrant = false,
  action = actionId,
): CaseCall {
  return {
    operation:
      kind === "set" ? "setProjectActionGrant" : "removeProjectActionGrant",
    path: {
      project_id: projectId,
      recipient_principal_id: recipientPrincipalId,
      action_id: action,
    },
    headers,
    ...(kind === "set"
      ? { body: { canGrant, expectedAccessRevision: revision } }
      : { query: { expectedAccessRevision: revision } }),
    timeout: 2000,
  };
}

function grantReceipt(
  kind: GrantChange,
  recipientPrincipalId: string,
  changed: boolean,
  canGrant = false,
): Record<string, JsonValue> {
  return {
    operationId: `sdk-project-grant-${kind}`,
    idempotencyExpiresAt: "2030-01-01T00:00:00Z",
    projectId,
    recipientPrincipalId,
    actionId,
    accessRevision: changed ? 8 : 7,
    changed,
    ...(kind === "set" ? { canGrant } : { removed: true }),
  };
}

function assertGrantRequest(
  witness: Record<string, JsonValue>,
  kind: GrantChange,
  recipient = grantRecipient,
  canGrant = false,
) {
  assertDispatch(
    witness,
    kind === "set" ? "PUT" : "DELETE",
    `/v1/projects/${projectId}/grants/${recipient}/${actionId}`,
  );
  assert.ok(
    witness.headers &&
      typeof witness.headers === "object" &&
      !Array.isArray(witness.headers),
  );
  assert.equal(witness.headers["idempotency-key"], "sdk-project-grant-key");
  if (kind === "set") {
    assertJsonBody(witness, { canGrant, expectedAccessRevision: 7 });
    assert.equal(witness.query, "");
  } else {
    assert.deepEqual(
      [...new URLSearchParams(String(witness.query))],
      [["expectedAccessRevision", "7"]],
    );
    assert.equal(witness.rawBodyBase64, "");
    assert.equal(witness.jsonBody, undefined);
  }
}

const changeFailures: {
  id: string;
  headers: Record<string, string>;
  status: number;
  code: string;
  recipient?: string;
  revision?: number;
  action?: string;
}[] = [
  {
    id: "unauthenticated",
    headers: { "Idempotency-Key": "sdk-project-grant-key" },
    status: 401,
    code: "http_error",
  },
  {
    id: "forbidden",
    headers: { ...grantHeaders, Authorization: "Bearer sdk-denied" },
    status: 403,
    code: "access_denied",
  },
  {
    id: "cookie-csrf",
    headers: {
      Cookie: "ory_kratos_session=sdk-cookie",
      "Idempotency-Key": "sdk-project-grant-key",
    },
    status: 403,
    code: "access_denied",
  },
  {
    id: "hidden-recipient",
    headers: grantHeaders,
    recipient: "00000000-0000-4000-8000-000000000099",
    status: 404,
    code: "resource_not_found",
  },
  {
    id: "stale",
    headers: grantHeaders,
    revision: 6,
    status: 409,
    code: "stale_revision",
  },
  {
    id: "unavailable",
    headers: { ...grantHeaders, Authorization: "Bearer sdk-unavailable" },
    status: 503,
    code: "dependency_unavailable",
  },
  {
    id: "exact-action-denied",
    headers: grantHeaders,
    action: "inspect-feedback",
    status: 403,
    code: "access_denied",
  },
  {
    id: "unsupported-action",
    headers: grantHeaders,
    action: "unknown-action",
    status: 422,
    code: "invalid_input",
  },
];

for (const { kind, operation } of changes) {
  for (const credential of ["bearer", "cookie"] as const)
    for (const changed of [true, false])
      sdkTest(
        {
          id: `project-action-grant-${kind}-${credential}${changed ? "" : "-unchanged"}`,
          operation,
          outcome: "success",
        },
        async ({ call, origin }) => {
          const recipient = changed ? grantRecipient : unchangedGrantRecipient;
          const headers =
            credential === "bearer"
              ? grantHeaders
              : {
                  Cookie: "ory_kratos_session=sdk-cookie",
                  Origin: origin,
                  "X-Inframeld-CSRF": "1",
                  "Idempotency-Key": "sdk-project-grant-key",
                };
          const { observation, witness } = await call(
            changeInput(kind, recipient, headers),
          );
          assert.deepEqual(
            assertSuccess(observation, kind === "set" && changed ? 201 : 200),
            grantReceipt(kind, recipient, changed),
          );
          assertGrantRequest(witness, kind, recipient);
          assert.deepEqual(headerValues(observation, "cache-control"), [
            "no-store",
          ]);
          if (credential === "cookie") {
            assert.equal(witness.origin, origin);
            assert.equal(witness.csrf, "1");
          }
        },
      );

  sdkTest(
    {
      id: `project-action-grant-${kind}-original-wire-result`,
      operation,
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ sequence }) => {
      const input = changeInput(kind, grantRecipient, grantHeaders);
      const results = await sequence([input, input]);
      assert.equal(results.length, 2);
      for (const { observation, witness } of results) {
        assert.deepEqual(
          assertSuccess(observation, kind === "set" ? 201 : 200),
          grantReceipt(kind, grantRecipient, true),
        );
        assertGrantRequest(witness, kind);
      }
    },
  );

  sdkTest(
    {
      id: `project-action-grant-${kind}-current-auth-before-original-result`,
      operation,
      outcome: "failure",
      expectedCalls: 2,
    },
    async ({ call }) => {
      const first = await call(changeInput(kind, grantRecipient, grantHeaders));
      assertSuccess(first.observation, kind === "set" ? 201 : 200);
      const denied = await call(
        changeInput(kind, grantRecipient, {
          ...grantHeaders,
          Authorization: "Bearer sdk-denied",
        }),
      );
      assert.equal(denied.observation.kind, "sdk-error");
      assert.equal(denied.observation.status, 403);
      assert.notEqual(denied.observation.validation, "none");
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

  for (const failure of changeFailures)
    sdkTest(
      {
        id: `project-action-grant-${kind}-${failure.id}`,
        operation,
        outcome: "failure",
      },
      async ({ call }) => {
        const { observation, witness } = await call(
          changeInput(
            kind,
            failure.recipient ?? grantRecipient,
            failure.headers,
            failure.revision ?? 7,
            false,
            failure.action ?? actionId,
          ),
        );
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
        assert.equal(witness.method, kind === "set" ? "PUT" : "DELETE");
        if (kind === "remove") assert.equal(witness.rawBodyBase64, "");
      },
    );

  const validReceipt = grantReceipt(kind, grantRecipient, true);
  const { idempotencyExpiresAt: _expiry, ...withoutExpiry } = validReceipt;
  for (const [id, body] of [
    ["missing-expiry", withoutExpiry],
    [
      "invalid-result-state",
      {
        ...validReceipt,
        ...(kind === "set" ? { canGrant: "false" } : { removed: false }),
      },
    ],
  ] satisfies [string, JsonValue][])
    sdkTest(
      {
        id: `project-action-grant-${kind}-${id}`,
        operation,
        outcome: "failure",
      },
      async ({ call }) => {
        const { observation } = await call({
          ...changeInput(kind, grantRecipient, grantHeaders),
          fault: { kind: "json", status: kind === "set" ? 201 : 200, body },
        });
        assert.equal(observation.kind, "sdk-error");
        assert.equal(observation.status, kind === "set" ? 201 : 200);
      },
    );
}

for (const [id, recipient, status] of [
  ["new-delegation", grantRecipient, 201],
  ["change-level", "00000000-0000-4000-8000-000000000006", 200],
] as const)
  sdkTest(
    {
      id: `project-action-grant-set-${id}`,
      operation: "setProjectActionGrant",
      outcome: "success",
    },
    async ({ call }) => {
      const { observation, witness } = await call(
        changeInput("set", recipient, grantHeaders, 7, true),
      );
      assert.deepEqual(
        assertSuccess(observation, status),
        grantReceipt("set", recipient, true, true),
      );
      assertGrantRequest(witness, "set", recipient, true);
    },
  );

for (const [id, recipient, status, code] of [
  [
    "ineligible-recipient",
    "00000000-0000-4000-8000-000000000007",
    409,
    "conflict",
  ],
  [
    "unsupported-recipient",
    "00000000-0000-4000-8000-000000000008",
    422,
    "invalid_input",
  ],
] as const)
  sdkTest(
    {
      id: `project-action-grant-set-${id}`,
      operation: "setProjectActionGrant",
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation } = await call(
        changeInput("set", recipient, grantHeaders),
      );
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(observation.body.code, code);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
