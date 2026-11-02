import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const organizationId = "00000000-0000-4000-8000-000000000002";
const projectId = "00000000-0000-4000-8000-000000000004";
const bearer = { Authorization: "Bearer sdk-human" };
const write = { ...bearer, "Idempotency-Key": "sdk-project-key" };
const ownAccess = {
  organizationId,
  principalId: "00000000-0000-4000-8000-000000000001",
  accessRevision: 7,
  grants: [{ actionId: "create-projects", canGrant: false }],
};
const input = {
  organizationId,
  expectedAccessRevision: 7,
  name: "new-support",
  displayName: "Support 🧭",
};
const actions = [
  "manage-project-members",
  "create-access-groups",
  "create-application-accounts",
  "create-pipelines",
  "create-deployments",
  "manage-upload-defaults",
  "delete-project",
  "inspect-budget",
  "manage-budget",
  "manage-trace-policy",
  "delete-trace-history",
  "inspect-feedback",
  "create-collections",
  "create-sources",
  "create-model-connections",
  "create-processing-profiles",
  "create-embedding-profiles",
  "edit-project-metadata",
];
const receipt = {
  operationId: "sdk-project-creation",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
  organizationId,
  projectId,
  name: input.name,
  displayName: input.displayName,
  accessRevision: 1,
  metadataRevision: 0,
  initialGrants: actions.map((actionId) => ({
    target: { kind: "project", projectId },
    actionId,
    canGrant: true,
  })),
};

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `organization-own-access-${credential}`,
      operation: "getMyOrganizationAccess",
      outcome: "success",
    },
    async ({ call }) => {
      const headers =
        credential === "bearer"
          ? bearer
          : { Cookie: "ory_kratos_session=sdk-cookie" };
      const { observation } = await call({
        operation: "getMyOrganizationAccess",
        headers,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 200), ownAccess);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

sdkTest(
  {
    id: "organization-own-access-empty",
    operation: "getMyOrganizationAccess",
    outcome: "success",
  },
  async ({ call }) => {
    const empty = { ...ownAccess, grants: [] };
    const { observation } = await call({
      operation: "getMyOrganizationAccess",
      headers: bearer,
      timeout: 2000,
      fault: { kind: "json", status: 200, body: empty },
    });
    assert.deepEqual(assertSuccess(observation, 200), empty);
  },
);

sdkTest(
  {
    id: "organization-own-access-denied",
    operation: "getMyOrganizationAccess",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "getMyOrganizationAccess",
      headers: { Authorization: "Bearer sdk-denied" },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
    assert.notEqual(observation.validation, "none");
  },
);

for (const credential of ["bearer", "cookie"] as const)
  sdkTest(
    {
      id: `project-create-${credential}`,
      operation: "createProject",
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
              "Idempotency-Key": "sdk-project-key",
            };
      const { observation, witness } = await call({
        operation: "createProject",
        headers,
        body: input,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(observation, 201), receipt);
      assertJsonBody(witness, input);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-project-key");
      if (credential === "cookie") {
        assert.equal(witness.origin, origin);
        assert.equal(witness.csrf, "1");
      }
    },
  );

sdkTest(
  {
    id: "project-create-original-receipt",
    operation: "createProject",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const call = {
      operation: "createProject" as const,
      headers: write,
      body: input,
      timeout: 2000,
    };
    const results = await sequence([call, call]);
    assert.equal(results.length, 2);
    for (const { observation, witness } of results) {
      assert.deepEqual(assertSuccess(observation, 201), receipt);
      assertJsonBody(witness, input);
    }
  },
);

sdkTest(
  {
    id: "project-create-cookie-csrf-denied",
    operation: "createProject",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "createProject",
      headers: {
        Cookie: "ory_kratos_session=sdk-cookie",
        "Idempotency-Key": "sdk-project-key",
      },
      body: input,
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
    assert.notEqual(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "project-create-rejects-false-initial-grant",
    operation: "createProject",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "createProject",
      headers: write,
      body: input,
      timeout: 2000,
      fault: {
        kind: "json",
        status: 201,
        body: {
          ...receipt,
          initialGrants: receipt.initialGrants.map((grant) => ({
            ...grant,
            canGrant: false,
          })),
        },
      },
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 201);
    assertJsonBody(witness, input);
  },
);
