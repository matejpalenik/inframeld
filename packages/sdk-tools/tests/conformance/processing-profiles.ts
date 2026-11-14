import assert from "node:assert/strict";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest } from "../../src/conformance/cases.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const processingProfileId = "00000000-0000-4000-8000-000000000032";
const collection = `/v1/projects/${projectId}/processing-profiles`;
const headers = { Authorization: "Bearer sdk-human" };
const request = {
  name: "handbook",
  displayName: "Support handbook",
  definition: {
    doclingSlimVersion: "2.148.0",
    doclingCoreVersion: "2.106.0",
    assetManifestSha256:
      "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
    maxContentTokens: 640,
    mergePeers: true,
    repeatTableHeader: false,
    ocrEnabled: false,
  },
};
const profile = { projectId, processingProfileId, ...request };

sdkTest(
  {
    id: "processing-profile-create",
    operation: "createProcessingProfile",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "createProcessingProfile",
      headers: { ...headers, "Idempotency-Key": "sdk-profile-create" },
      path: { project_id: projectId },
      body: request,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 201), {
      profile,
      operationId: "sdk-processing-profile-create",
      idempotencyExpiresAt: "2030-01-01T00:00:00Z",
      projectAccessRevision: 8,
      initialGrants: ["view-processing-profile", "use-processing-profile"].map(
        (actionId) => ({
          target: { kind: "processing-profile", processingProfileId },
          actionId,
          canGrant: true,
        }),
      ),
    });
    assertDispatch(witness, "POST", collection);
    assertJsonBody(witness, request);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "processing-profile-get",
    operation: "getProcessingProfile",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getProcessingProfile",
      headers,
      path: {
        project_id: projectId,
        processing_profile_id: processingProfileId,
      },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), profile);
    assertDispatch(witness, "GET", `${collection}/${processingProfileId}`);
  },
);

sdkTest(
  {
    id: "processing-profile-list",
    operation: "listProcessingProfiles",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listProcessingProfiles",
      headers,
      path: { project_id: projectId },
      query: { limit: 1, cursor: "profile-cursor_2" },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [profile],
      nextCursor: null,
    });
    assertDispatch(witness, "GET", collection);
    assert.deepEqual([...new URLSearchParams(String(witness.query))].sort(), [
      ["cursor", "profile-cursor_2"],
      ["limit", "1"],
    ]);
  },
);

const recipient = "00000000-0000-4000-8000-000000000006";
const actionId = "view-processing-profile";
const grants = `/v1/processing-profiles/${processingProfileId}/grants`;
const grant = `${grants}/${recipient}/${actionId}`;
const grantPath = {
  processing_profile_id: processingProfileId,
  recipient_principal_id: recipient,
  action_id: actionId,
};
const original = {
  operation: "setProcessingProfileActionGrant",
  headers: { ...headers, "Idempotency-Key": "sdk-profile-view-original" },
  path: grantPath,
  body: { expectedAccessRevision: 7, canGrant: false },
  timeout: 2000,
} as const;

sdkTest(
  {
    id: "processing-profile-grant-original-wire-result",
    operation: original.operation,
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const results = await sequence([original, original]);
    for (const { observation, witness } of results) {
      assert.deepEqual(assertSuccess(observation, 201), {
        processingProfileId,
        recipientPrincipalId: recipient,
        actionId,
        canGrant: false,
        changed: true,
        accessRevision: 8,
        operationId: "sdk-processing-profile-grant-put",
        idempotencyExpiresAt: "2030-01-01T00:00:00Z",
      });
      assertDispatch(witness, "PUT", grant);
      assertJsonBody(witness, original.body);
      assert.equal(witness.authorization, headers.Authorization);
      assert.ok(
        witness.headers &&
          typeof witness.headers === "object" &&
          !Array.isArray(witness.headers),
      );
      assert.equal(
        witness.headers["idempotency-key"],
        original.headers["Idempotency-Key"],
      );
    }
  },
);

for (const [failure, status, code] of [
  ["scope", 403, "access_denied"],
  ["revision", 409, "stale_revision"],
] as const) {
  sdkTest(
    {
      id: `processing-profile-grant-${failure}`,
      operation: original.operation,
      outcome: "failure",
    },
    async ({ call }) => {
      const input = {
        ...original,
        headers: {
          Authorization: `Bearer ${failure === "scope" ? "sdk-other-human" : "sdk-human"}`,
          "Idempotency-Key": `sdk-profile-${failure}`,
        },
        body: { ...original.body, expectedAccessRevision: 6 },
      };
      const { observation, witness } = await call(input);
      assert.equal(observation.kind, "sdk-error");
      assert.equal(observation.status, status);
      assert.notEqual(observation.validation, "none");
      assert.ok(
        observation.body &&
          typeof observation.body === "object" &&
          !Array.isArray(observation.body),
      );
      assert.equal(observation.body.code, code);
      assertDispatch(witness, "PUT", grant);
      assertJsonBody(witness, input.body);
    },
  );
}
