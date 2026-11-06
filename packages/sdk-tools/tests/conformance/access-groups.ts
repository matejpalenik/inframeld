import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const groupId = "00000000-0000-4000-8000-000000000007";
const principalId = "00000000-0000-4000-8000-000000000001";
const applicationId = "00000000-0000-4000-8000-000000000008";
const root = `/v1/projects/${projectId}/access-groups`;
const bearer = { Authorization: "Bearer sdk-human" };
const write = { ...bearer, "Idempotency-Key": "sdk-group-create" };
const input = {
  name: "support-knowledge",
  displayName: "SupportKnowledge 🧭",
  expectedAccessRevision: 7,
};
const base = {
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  projectId,
  accessGroupId: groupId,
  accessRevision: 8,
};
const metadata = {
  projectId,
  accessGroupId: groupId,
  name: "support-knowledge",
  displayName: "SupportKnowledge",
  createdAt: "2030-01-01T00:00:00Z",
  accessRevision: 8,
};

for (const credential of ["bearer", "cookie"] as const) {
  sdkTest(
    {
      id: `group-create-${credential}`,
      operation: "createAccessGroup",
      outcome: "success",
    },
    async ({ call, origin }) => {
      const headers =
        credential === "bearer"
          ? write
          : {
              Cookie: "ory_kratos_session=sdk-cookie",
              Origin: origin,
              "X-Inframeld-CSRF": "1",
              "Idempotency-Key": "sdk-group-create",
            };
      const { observation, witness } = await call({
        operation: "createAccessGroup",
        path: { project_id: projectId },
        headers,
        body: input,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 201), {
        ...base,
        operationId: "sdk-group-create",
        name: input.name,
        displayName: input.displayName,
        creatorPrincipalId: principalId,
      });
      assertDispatch(witness, "POST", root);
      assertJsonBody(witness, input);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

for (const operation of ["getAccessGroup", "resolveAccessGroup"] as const) {
  sdkTest(
    { id: `group-metadata-${operation}`, operation, outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation,
        path: {
          project_id: projectId,
          ...(operation === "getAccessGroup"
            ? { access_group_id: groupId }
            : {}),
        },
        query:
          operation === "resolveAccessGroup"
            ? { name: "support-knowledge" }
            : {},
        headers: bearer,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), metadata);
      assertDispatch(
        witness,
        "GET",
        operation === "getAccessGroup"
          ? `${root}/${groupId}`
          : `${root}/resolve`,
      );
    },
  );
}

sdkTest(
  {
    id: "group-legacy-null-name",
    operation: "getAccessGroup",
    outcome: "success",
  },
  async ({ call }) => {
    const legacy = "00000000-0000-4000-8000-000000000005";
    const { observation } = await call({
      operation: "getAccessGroup",
      path: { project_id: projectId, access_group_id: legacy },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      ...metadata,
      accessGroupId: legacy,
      name: null,
      displayName: "ExistingGroup",
    });
  },
);

for (const [operation, collection] of [
  ["listAccessGroupMembers", "members"],
  ["listAccessGroupManagers", "managers"],
] as const) {
  sdkTest(
    { id: `group-page-${collection}`, operation, outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation,
        path: { project_id: projectId, access_group_id: groupId },
        query: { limit: 1 },
        headers: bearer,
        timeout: 2000,
      });
      const page = assertSuccess(observation, 200);
      assert.deepEqual(page, {
        projectId,
        accessGroupId: groupId,
        accessRevision: 8,
        items: [{ principalId, kind: "human", displayName: "Alice" }],
        nextCursor: collection === "members" ? "Y29udGludWU" : null,
      });
      assertDispatch(witness, "GET", `${root}/${groupId}/${collection}`);
      assert.equal(
        new URLSearchParams(String(witness.query)).get("limit"),
        "1",
      );
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

sdkTest(
  {
    id: "group-page-application-continuation",
    operation: "listAccessGroupMembers",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listAccessGroupMembers",
      path: { project_id: projectId, access_group_id: groupId },
      query: { limit: 100, cursor: "Y29udGludWU" },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      projectId,
      accessGroupId: groupId,
      accessRevision: 8,
      items: [
        {
          principalId: applicationId,
          kind: "application",
          displayName: "SupportBot",
        },
      ],
      nextCursor: null,
    });
    assert.equal(
      new URLSearchParams(String(witness.query)).get("cursor"),
      "Y29udGludWU",
    );
  },
);

for (const [operation, collection, kind, field] of [
  ["addAccessGroupMember", "members", "add-member", "member"],
  ["appointAccessGroupManager", "managers", "appoint-manager", "manager"],
] as const) {
  for (const changed of [true, false]) {
    sdkTest(
      {
        id: `group-${kind}-${changed ? "changed" : "unchanged"}`,
        operation,
        outcome: "success",
      },
      async ({ call }) => {
        const body = { expectedAccessRevision: 7 };
        const { observation, witness } = await call({
          operation,
          path: {
            project_id: projectId,
            access_group_id: groupId,
            principal_id: principalId,
          },
          body,
          headers: {
            ...bearer,
            "Idempotency-Key": changed ? "sdk-group-change" : "sdk-group-noop",
          },
          timeout: 2000,
        });
        assert.deepEqual(assertSuccess(observation, changed ? 201 : 200), {
          ...base,
          operationId: `sdk-group-${kind}`,
          principalId,
          accessRevision: changed ? 8 : 7,
          [field]: true,
          changed,
        });
        assertDispatch(
          witness,
          "PUT",
          `${root}/${groupId}/${collection}/${principalId}`,
        );
        assertJsonBody(witness, body);
      },
    );
  }
}

for (const [operation, collection, kind] of [
  ["removeAccessGroupMember", "members", "remove-member"],
  ["removeAccessGroupManager", "managers", "remove-manager"],
] as const) {
  sdkTest(
    { id: `group-${kind}-query`, operation, outcome: "success" },
    async ({ call }) => {
      const { observation, witness } = await call({
        operation,
        path: {
          project_id: projectId,
          access_group_id: groupId,
          principal_id: principalId,
        },
        query: { expectedAccessRevision: 7 },
        headers: write,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), {
        ...base,
        operationId: `sdk-group-${kind}`,
        principalId,
        removed: true,
        changed: true,
      });
      assertDispatch(
        witness,
        "DELETE",
        `${root}/${groupId}/${collection}/${principalId}`,
      );
      assert.equal(
        new URLSearchParams(String(witness.query)).get(
          "expectedAccessRevision",
        ),
        "7",
      );
      assert.equal(witness.rawBodyBase64, "");
    },
  );
}

sdkTest(
  {
    id: "group-delete-query",
    operation: "deleteAccessGroup",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "deleteAccessGroup",
      path: { project_id: projectId, access_group_id: groupId },
      query: { expectedAccessRevision: 7 },
      headers: { ...bearer, "Idempotency-Key": "sdk-group-delete" },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      ...base,
      operationId: "sdk-group-delete",
      removed: true,
    });
    assertDispatch(witness, "DELETE", `${root}/${groupId}`);
    assert.equal(
      new URLSearchParams(String(witness.query)).get("expectedAccessRevision"),
      "7",
    );
    assert.equal(witness.rawBodyBase64, "");
  },
);

sdkTest(
  {
    id: "group-delete-original-identity-retained-projection",
    operation: "lookupOriginalOperation",
    outcome: "success",
  },
  async ({ call }) => {
    const body = {
      installationId: "00000000-0000-4000-8000-000000000001",
      organizationId: "00000000-0000-4000-8000-000000000002",
      projectId,
      method: "DELETE",
      requestedRoute: `${root}/${groupId}`,
      key: "sdk-group-delete",
      expectedAuthority: {
        family: "access_group_deletion",
        actionId: "delete-access-group",
      },
    };
    const { observation, witness } = await call({
      operation: "lookupOriginalOperation",
      headers: bearer,
      body,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      outcome: "retained",
      operationId: "sdk-group-delete",
      jobState: null,
      admissionConfirmed: true,
      accessBlocked: true,
      applicationShutdownComplete: null,
      physicalCleanupComplete: true,
      retentionExpiresAt: "2030-01-31T00:00:00Z",
    });
    assertJsonBody(witness, body);
  },
);

sdkTest(
  {
    id: "group-manager-application-denied",
    operation: "appointAccessGroupManager",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "appointAccessGroupManager",
      path: {
        project_id: projectId,
        access_group_id: groupId,
        principal_id: applicationId,
      },
      headers: write,
      body: { expectedAccessRevision: 7 },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 422);
    assert.notEqual(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "group-cookie-csrf-denied",
    operation: "createAccessGroup",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "createAccessGroup",
      path: { project_id: projectId },
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-group-create",
      },
      body: input,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
  },
);

sdkTest(
  {
    id: "group-name-unresolved",
    operation: "resolveAccessGroup",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "resolveAccessGroup",
      path: { project_id: projectId },
      query: { name: "missing" },
      headers: bearer,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 404);
  },
);

sdkTest(
  {
    id: "group-missing-required-nullable-name",
    operation: "getAccessGroup",
    outcome: "failure",
  },
  async ({ call }) => {
    const { name: _name, ...missing } = metadata;
    const { observation } = await call({
      operation: "getAccessGroup",
      path: { project_id: projectId, access_group_id: groupId },
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: missing },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
  },
);

sdkTest(
  {
    id: "group-delete-known-status-matches-retained-lookup",
    operation: "getDeletionStatus",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getDeletionStatus",
      query: { operationId: "sdk-group-delete" },
      headers: bearer,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      outcome: "retained",
      operationId: "sdk-group-delete",
      jobState: null,
      admissionConfirmed: true,
      accessBlocked: true,
      applicationShutdownComplete: null,
      physicalCleanupComplete: true,
      retentionExpiresAt: "2030-01-31T00:00:00Z",
    });
  },
);

sdkTest(
  {
    id: "group-lookup-rejects-missing-required-nullable-shutdown",
    operation: "lookupOriginalOperation",
    outcome: "failure",
  },
  async ({ call }) => {
    const body = {
      installationId: "00000000-0000-4000-8000-000000000001",
      organizationId: "00000000-0000-4000-8000-000000000002",
      projectId,
      method: "DELETE",
      requestedRoute: `${root}/${groupId}`,
      key: "sdk-group-delete",
      expectedAuthority: {
        family: "access_group_deletion",
        actionId: "delete-access-group",
      },
    };
    const { observation } = await call({
      operation: "lookupOriginalOperation",
      headers: bearer,
      body,
      timeout: 2000,
      fault: {
        kind: "json",
        status: 200,
        body: {
          outcome: "retained",
          operationId: "sdk-group-delete",
          jobState: null,
          admissionConfirmed: true,
          accessBlocked: true,
          physicalCleanupComplete: true,
          retentionExpiresAt: "2030-01-31T00:00:00Z",
        },
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 200);
  },
);
