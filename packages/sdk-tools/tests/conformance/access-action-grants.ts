import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";

const installationId = "00000000-0000-4000-8000-000000000001";
const organizationId = "00000000-0000-4000-8000-000000000002";
const projectId = "00000000-0000-4000-8000-000000000003";
const recipientPrincipalId = "00000000-0000-4000-8000-000000000004";
const unchangedRecipient = "00000000-0000-4000-8000-000000000005";
const groupId = "00000000-0000-4000-8000-000000000007";
const applicationPrincipalId = "00000000-0000-4000-8000-000000000008";
const bearer = { Authorization: "Bearer sdk-human" };
const expires = "2030-01-01T00:00:00Z";

const families = [
  {
    slug: "organization",
    path: { organization_id: organizationId },
    scope: { organizationId },
    route: `/v1/organizations/${organizationId}/grants`,
    actionId: "create-projects",
    list: "listOrganizationActionGrants",
    set: "setOrganizationActionGrant",
    remove: "removeOrganizationActionGrant",
    lookup: "organization_grant_read",
    lookupProject: null,
  },
  {
    slug: "access-group",
    path: { project_id: projectId, access_group_id: groupId },
    scope: { projectId, accessGroupId: groupId },
    route: `/v1/projects/${projectId}/access-groups/${groupId}/grants`,
    actionId: "add-documents",
    list: "listAccessGroupActionGrants",
    set: "setAccessGroupActionGrant",
    remove: "removeAccessGroupActionGrant",
    lookup: "access_group_grant_read",
    lookupProject: projectId,
  },
  {
    slug: "application-account",
    path: {
      project_id: projectId,
      application_principal_id: applicationPrincipalId,
    },
    scope: { projectId, applicationPrincipalId },
    route: `/v1/projects/${projectId}/application-accounts/${applicationPrincipalId}/grants`,
    actionId: "issue-application-keys",
    list: "listApplicationAccountActionGrants",
    set: "setApplicationAccountActionGrant",
    remove: "removeApplicationAccountActionGrant",
    lookup: "application_account_grant_read",
    lookupProject: projectId,
  },
] as const;

for (const family of families) {
  const actionId = family.actionId;
  const headers = {
    ...bearer,
    "Idempotency-Key": `sdk-${family.slug}-grant-key`,
  };

  sdkTest(
    {
      id: `${family.slug}-grants-page`,
      operation: family.list,
      outcome: "success",
    },
    async ({ call }) => {
      const cursor = "native_cursor-escaped";
      const result = await call({
        operation: family.list,
        path: family.path,
        query: { actionId, limit: 1, cursor },
        headers: bearer,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(result.observation, 200), {
        items: [
          { ...family.scope, recipientPrincipalId, actionId, canGrant: true },
        ],
        nextCursor: null,
      });
      assertDispatch(result.witness, "GET", family.route);
      const query = new URLSearchParams(String(result.witness.query));
      assert.deepEqual([...query].sort(), [
        ["actionId", actionId],
        ["cursor", cursor],
        ["limit", "1"],
      ]);
      assert.equal(result.witness.rawBodyBase64, "");
      assert.deepEqual(headerValues(result.observation, "cache-control"), [
        "no-store",
      ]);
    },
  );

  sdkTest(
    {
      id: `${family.slug}-grant-created-and-noop`,
      operation: family.set,
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ call }) => {
      for (const [recipient, canGrant, status, changed] of [
        [recipientPrincipalId, true, 201, true],
        [unchangedRecipient, false, 200, false],
      ] as const) {
        const body = { canGrant, expectedAccessRevision: 7 };
        const result = await call({
          operation: family.set,
          path: {
            ...family.path,
            recipient_principal_id: recipient,
            action_id: actionId,
          },
          headers,
          body,
          timeout: 2000,
        });
        assert.deepEqual(assertSuccess(result.observation, status), {
          ...family.scope,
          recipientPrincipalId: recipient,
          actionId,
          canGrant,
          changed,
          accessRevision: changed ? 8 : 7,
          operationId: `sdk-${family.slug}-grant-put`,
          idempotencyExpiresAt: expires,
        });
        assertDispatch(
          result.witness,
          "PUT",
          `${family.route}/${recipient}/${actionId}`,
        );
        assertJsonBody(result.witness, body);
        assert.equal(result.witness.query, "");
        assert.deepEqual(headerValues(result.observation, "cache-control"), [
          "no-store",
        ]);
      }
    },
  );

  sdkTest(
    {
      id: `${family.slug}-grant-removal`,
      operation: family.remove,
      outcome: "success",
    },
    async ({ call }) => {
      const result = await call({
        operation: family.remove,
        path: {
          ...family.path,
          recipient_principal_id: recipientPrincipalId,
          action_id: actionId,
        },
        headers,
        query: { expectedAccessRevision: 7 },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(result.observation, 200), {
        ...family.scope,
        recipientPrincipalId,
        actionId,
        removed: true,
        changed: true,
        accessRevision: 8,
        operationId: `sdk-${family.slug}-grant-delete`,
        idempotencyExpiresAt: expires,
      });
      assertDispatch(
        result.witness,
        "DELETE",
        `${family.route}/${recipientPrincipalId}/${actionId}`,
      );
      assert.equal(result.witness.rawBodyBase64, "");
      assert.deepEqual(
        [...new URLSearchParams(String(result.witness.query))],
        [["expectedAccessRevision", "7"]],
      );
    },
  );

  sdkTest(
    {
      id: `${family.slug}-grant-original-lookup`,
      operation: "lookupOriginalOperation",
      outcome: "success",
    },
    async ({ call }) => {
      const body = {
        installationId,
        organizationId,
        projectId: family.lookupProject,
        method: "PUT",
        requestedRoute: `${family.route}/${recipientPrincipalId}/${actionId}`,
        key: headers["Idempotency-Key"],
        expectedAuthority: { family: family.lookup, actionId },
      };
      const result = await call({
        operation: "lookupOriginalOperation",
        headers: bearer,
        body,
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(result.observation, 200), {
        operationId: `sdk-${family.slug}-grant-put`,
        outcome: "completed_synchronous",
        classification: "safe_result",
        idempotencyExpiresAt: expires,
      });
      assertJsonBody(result.witness, body);
      assert.deepEqual(headerValues(result.observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
}

for (const [targetKind, targetId, actionId] of [
  ["project", projectId, "create-access-groups"],
  ["access-group", groupId, "add-documents"],
  ["application-account", applicationPrincipalId, "issue-application-keys"],
] as const)
  sdkTest(
    {
      id: `grant-recipients-${targetKind}`,
      operation: "listProjectGrantRecipients",
      outcome: "success",
    },
    async ({ call }) => {
      const result = await call({
        operation: "listProjectGrantRecipients",
        path: { project_id: projectId },
        headers: bearer,
        query: { targetKind, targetId, actionId, limit: 1 },
        timeout: 2000,
      });
      assert.deepEqual(assertSuccess(result.observation, 200), {
        items: [
          {
            principalId: recipientPrincipalId,
            displayName: "Bob",
            kind: "human",
          },
        ],
        nextCursor: null,
      });
      assertDispatch(
        result.witness,
        "GET",
        `/v1/projects/${projectId}/grant-recipients`,
      );
      const query = new URLSearchParams(String(result.witness.query));
      assert.deepEqual([...query].sort(), [
        ["actionId", actionId],
        ["limit", "1"],
        ["targetId", targetId],
        ["targetKind", targetKind],
      ]);
      assert.equal(result.witness.rawBodyBase64, "");
      assert.deepEqual(headerValues(result.observation, "cache-control"), [
        "no-store",
      ]);
    },
  );
