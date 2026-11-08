import assert from "node:assert/strict";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest } from "../../src/conformance/cases.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";
import { budgets } from "../../src/system/budgets.ts";

const organizationId = "00000000-0000-4000-8000-000000000002";
const projectId = "00000000-0000-4000-8000-000000000003";
const principalId = "00000000-0000-4000-8000-000000000004";
const invitationId = "00000000-0000-4000-8000-000000000006";
const accessGroupId = "00000000-0000-4000-8000-000000000007";
const applicationPrincipalId = "00000000-0000-4000-8000-000000000008";
const unknownId = "00000000-0000-4000-8000-000000000099";
const expires = "2030-01-01T00:00:00Z";
const invitationToken = "A".repeat(43);
const bearer = { Authorization: "Bearer sdk-human" };
const cookie = { Cookie: "ory_kratos_session=sdk-cookie" };
const admission = {
  organizationId,
  expectedAccessRevision: 7,
  expectedProjectAccessRevisions: [],
  assignments: [{ kind: "admission-only" }],
};
const accessAssignments: Record<string, JsonValue>[] = [
  { kind: "project-membership", projectId },
  { kind: "group-membership", projectId, accessGroupId },
  { kind: "group-manager", projectId, accessGroupId },
  {
    kind: "action-grant",
    target: { kind: "organization", organizationId },
    actionId: "create-projects",
    canGrant: false,
  },
  {
    kind: "action-grant",
    target: { kind: "project", projectId },
    actionId: "create-access-groups",
    canGrant: true,
  },
  {
    kind: "action-grant",
    target: { kind: "access-group", projectId, accessGroupId },
    actionId: "add-documents",
    canGrant: true,
  },
  {
    kind: "action-grant",
    target: { kind: "application-account", projectId, applicationPrincipalId },
    actionId: "issue-application-keys",
    canGrant: true,
  },
];
// Future targets qualify generated representations, without pretending their owners exist.
const futureAssignments: Record<string, JsonValue>[] = [
  ["pipeline", "pipelineId", "query"],
  ["deployment", "deploymentId", "query"],
  ["collection", "collectionId", "view-collection"],
  ["source", "sourceId", "view-source-configuration"],
  ["model-connection", "modelConnectionId", "use-model-connection"],
  ["processing-profile", "processingProfileId", "use-processing-profile"],
  ["embedding-profile", "embeddingProfileId", "use-embedding-profile"],
].map(([kind, field, actionId], index) => ({
  kind: "action-grant",
  target: { kind: kind!, [field!]: unknownId },
  actionId: actionId!,
  canGrant: index % 2 === 0,
}));

sdkTest(
  {
    id: "invitation-issue-wire-alternatives",
    operation: "issueInvitation",
    outcome: "success",
    expectedCalls: 4,
  },
  async ({ sequence }) => {
    const mixed = {
      ...admission,
      assignments: [...accessAssignments, ...futureAssignments],
      expectedProjectAccessRevisions: [{ projectId, accessRevision: 11 }],
      expiresInSeconds: 3600,
    };
    const inputs = [
      admission,
      admission,
      mixed,
      { ...admission, organizationId: unknownId },
    ];
    const keys = [
      "sdk-invitation-first",
      "sdk-invitation-replay",
      "sdk-invitation-mixed",
      "sdk-invitation-hidden",
    ];
    const results = await sequence(
      inputs.map((body, index) => ({
        operation: "issueInvitation",
        body,
        headers: { ...bearer, "Idempotency-Key": keys[index]! },
        timeout: budgets.case,
      })),
    );
    assert.equal(results.length, inputs.length);
    for (const [index, { observation, witness }] of results.entries()) {
      const input = inputs[index]!;
      if (index === 3) {
        assert.equal(observation.kind, "sdk-error");
        assert.equal(observation.status, 404);
        assert.ok(
          ["generated-model", "generated-schema"].includes(
            observation.validation,
          ),
        );
        assert.ok(
          observation.body &&
            typeof observation.body === "object" &&
            !Array.isArray(observation.body),
        );
        assert.equal(observation.body.status, 404);
        assert.equal(observation.body.code, "resource_not_found");
      } else {
        const replay = index === 1;
        const body = assertSuccess(observation, 201);
        assert.deepEqual(body, {
          invitationId,
          organizationId,
          assignments: input.assignments,
          expiresAt: expires,
          accessRevision: 8,
          operationId: "sdk-invitation-issue",
          idempotencyExpiresAt: expires,
          secretAvailable: !replay,
          ...(replay ? {} : { invitationToken }),
        });
        assert.equal(Object.hasOwn(body, "invitationToken"), !replay);
      }
      assertDispatch(witness, "POST", "/v1/invitations");
      assertJsonBody(witness, input);
      assert.equal(witness.query, "");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], keys[index]);
      assert.equal(witness.headers.authorization, bearer.Authorization);
      assert.ok(!Object.hasOwn(witness.headers, "cookie"));
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
    // Omission must survive generated construction rather than becoming explicit null.
    const firstBody = results[0]!.witness.jsonBody;
    assert.ok(
      firstBody && typeof firstBody === "object" && !Array.isArray(firstBody),
    );
    assert.ok(!Object.hasOwn(firstBody, "expiresInSeconds"));
  },
);

sdkTest(
  {
    id: "invitation-revoke-wire-outcomes",
    operation: "revokeInvitation",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const body = { expectedAccessRevision: 7 };
    const identifiers = [invitationId, unknownId];
    const results = await sequence(
      identifiers.map((id) => ({
        operation: "revokeInvitation",
        path: { invitation_id: id },
        body,
        headers: { ...bearer, "Idempotency-Key": "sdk-revoke-key" },
        timeout: budgets.case,
      })),
    );
    assert.equal(results.length, 2);
    assert.deepEqual(assertSuccess(results[0]!.observation, 200), {
      invitationId,
      organizationId,
      accessRevision: 8,
      operationId: "sdk-invitation-revoke",
      idempotencyExpiresAt: expires,
      revoked: true,
    });
    const denied = results[1]!.observation;
    assert.equal(denied.kind, "sdk-error");
    assert.equal(denied.status, 404);
    assert.ok(
      ["generated-model", "generated-schema"].includes(denied.validation),
    );
    assert.ok(
      denied.body &&
        typeof denied.body === "object" &&
        !Array.isArray(denied.body),
    );
    assert.equal(denied.body.status, 404);
    assert.equal(denied.body.code, "resource_not_found");
    for (const [index, { observation, witness }] of results.entries()) {
      assertDispatch(
        witness,
        "POST",
        `/v1/invitations/${identifiers[index]}/revoke`,
      );
      assertJsonBody(witness, body);
      assert.equal(witness.query, "");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-revoke-key");
      assert.equal(witness.headers.authorization, bearer.Authorization);
      assert.ok(!Object.hasOwn(witness.headers, "cookie"));
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);

sdkTest(
  {
    id: "invitation-preview-wire-outcomes",
    operation: "previewInvitation",
    outcome: "success",
    expectedCalls: 3,
  },
  async ({ sequence, origin }) => {
    const headers = { ...cookie, Origin: origin, "X-Inframeld-CSRF": "1" };
    const inputs = [
      { body: { invitationToken }, headers },
      { body: { invitationToken }, headers: { ...cookie, Origin: origin } },
      { body: { invitationToken: "E".repeat(43) }, headers },
    ];
    const results = await sequence(
      inputs.map((input) => ({
        operation: "previewInvitation",
        ...input,
        timeout: budgets.case,
      })),
    );
    assert.equal(results.length, 3);
    assert.deepEqual(assertSuccess(results[0]!.observation, 200), {
      invitationId,
      organizationId,
      assignments: accessAssignments,
      expiresAt: expires,
      scopes: [
        {
          target: { kind: "organization", organizationId },
          displayName: "Example Organization",
        },
        {
          target: { kind: "project", projectId },
          displayName: "Example Project",
        },
        {
          target: { kind: "access-group", projectId, accessGroupId },
          displayName: "Example Group",
        },
        {
          target: {
            kind: "application-account",
            projectId,
            applicationPrincipalId,
          },
          displayName: "Example Account",
        },
      ],
    });
    for (const [index, { observation, witness }] of results.entries()) {
      if (index > 0) {
        assert.equal(observation.kind, "sdk-error");
        assert.equal(observation.status, index === 1 ? 403 : 404);
        assert.ok(
          ["generated-model", "generated-schema"].includes(
            observation.validation,
          ),
        );
        assert.ok(
          observation.body &&
            typeof observation.body === "object" &&
            !Array.isArray(observation.body),
        );
        assert.equal(observation.body.status, index === 1 ? 403 : 404);
        assert.equal(
          observation.body.code,
          index === 1 ? "access_denied" : "resource_not_found",
        );
      }
      assertDispatch(witness, "POST", "/v1/invitations/preview");
      assertJsonBody(witness, inputs[index]!.body);
      assert.equal(witness.query, "");
      assert.equal(witness.origin, origin);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.ok(!Object.hasOwn(witness.headers, "idempotency-key"));
      assert.equal(witness.headers.cookie, cookie.Cookie);
      assert.ok(!Object.hasOwn(witness.headers, "authorization"));
      assert.equal(witness.csrf, index === 1 ? "" : "1");
      if (index === 1)
        assert.ok(!Object.hasOwn(witness.headers, "x-inframeld-csrf"));
      else assert.equal(witness.headers["x-inframeld-csrf"], "1");
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);

sdkTest(
  {
    id: "invitation-activate-wire-outcomes",
    operation: "activateInvitation",
    outcome: "success",
    expectedCalls: 3,
  },
  async ({ sequence, origin }) => {
    const headers = {
      ...cookie,
      Origin: origin,
      "X-Inframeld-CSRF": "1",
      "Idempotency-Key": "sdk-activate-key",
    };
    const inputs = [
      { invitationToken },
      { invitationToken },
      { invitationToken: "E".repeat(43) },
    ];
    // Repeated snapshots qualify generated client reuse. PostgreSQL owns original recovery.
    const results = await sequence(
      inputs.map((body) => ({
        operation: "activateInvitation",
        body,
        headers,
        timeout: budgets.case,
      })),
    );
    assert.equal(results.length, 3);
    for (const [index, { observation, witness }] of results.entries()) {
      if (index === 2) {
        assert.equal(observation.kind, "sdk-error");
        assert.equal(observation.status, 404);
        assert.ok(
          ["generated-model", "generated-schema"].includes(
            observation.validation,
          ),
        );
        assert.ok(
          observation.body &&
            typeof observation.body === "object" &&
            !Array.isArray(observation.body),
        );
        assert.equal(observation.body.status, 404);
        assert.equal(observation.body.code, "resource_not_found");
      } else {
        assert.deepEqual(assertSuccess(observation, 200), {
          invitationId,
          organizationId,
          principalId,
          organizationAccessRevision: 8,
          projectAccessRevisions: [{ projectId, accessRevision: 9 }],
          operationId: "sdk-invitation-activate",
          idempotencyExpiresAt: expires,
        });
      }
      assertDispatch(witness, "POST", "/v1/invitations/activate");
      assertJsonBody(witness, inputs[index]!);
      assert.equal(witness.origin, origin);
      assert.equal(witness.csrf, "1");
      assert.equal(witness.query, "");
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(witness.headers["idempotency-key"], "sdk-activate-key");
      assert.equal(witness.headers.cookie, cookie.Cookie);
      assert.ok(!Object.hasOwn(witness.headers, "authorization"));
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);
