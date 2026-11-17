import assert from "node:assert/strict";
import {
  assertDispatch,
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest } from "../../src/conformance/cases.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const embeddingProfileId = "00000000-0000-4000-8000-000000000249";
const collection = `/v1/projects/${projectId}/embedding-profiles`;
const path = { project_id: projectId };
const headers = { Authorization: "Bearer sdk-human" };
const createKey = "sdk-embedding-profile-create";
const request = {
  name: "support-embeddings",
  displayName: "Support embeddings",
  definition: {
    modelConnectionId: "00000000-0000-4000-8000-000000000030",
    model: "text-embedding-3-small",
    dimensions: 1536,
    normalization: "l2",
    distance: "cosine",
    documentPrefix: "  passage: é\n",
    queryPrefix: " query: ",
    contextTokens: 8191,
  },
};
const profile = {
  ...request,
  projectId,
  embeddingProfileId,
  definition: {
    ...request.definition,
    role: "embedding",
    expectedProvider: "openai",
    expectedModelRevision: null,
    tokenBound: {
      kind: "exact",
      implementation: "tiktoken/cl100k_base",
      revision:
        "0.14.0:sha256:223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    },
  },
  vectorIndexId: "00000000-0000-4000-8000-000000000247",
  vectorLayoutId: "00000000-0000-4000-8000-000000000248",
  placementVersion: 1,
  shardCount: 2,
};

sdkTest(
  {
    id: "embedding-profile-create",
    operation: "createEmbeddingProfile",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "createEmbeddingProfile",
      headers: { ...headers, "Idempotency-Key": createKey },
      path,
      body: request,
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 201), {
      profile,
      operationId: createKey,
      idempotencyExpiresAt: "2030-01-01T00:00:00Z",
      projectAccessRevision: 8,
      initialGrants: ["view-embedding-profile", "use-embedding-profile"].map(
        (actionId) => ({
          target: { kind: "embedding-profile", embeddingProfileId },
          actionId,
          canGrant: true,
        }),
      ),
    });
    assertDispatch(witness, "POST", collection);
    assertJsonBody(witness, request);
    assert.ok(
      witness.headers &&
        typeof witness.headers === "object" &&
        !Array.isArray(witness.headers),
    );
    assert.equal(witness.headers["idempotency-key"], createKey);
    assert.equal(witness.authorization, headers.Authorization);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "embedding-profile-get",
    operation: "getEmbeddingProfile",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "getEmbeddingProfile",
      headers,
      path: { ...path, embedding_profile_id: embeddingProfileId },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), profile);
    assertDispatch(witness, "GET", `${collection}/${embeddingProfileId}`);
    assert.equal(witness.authorization, headers.Authorization);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);

sdkTest(
  {
    id: "embedding-profile-list",
    operation: "listEmbeddingProfiles",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "listEmbeddingProfiles",
      headers,
      path,
      query: { limit: 1, cursor: "embedding-test-page" },
      timeout: 2000,
    });
    assert.deepEqual(assertSuccess(observation, 200), {
      items: [profile],
      nextCursor: null,
    });
    assertDispatch(witness, "GET", collection);
    assert.equal(witness.authorization, headers.Authorization);
    assert.deepEqual([...new URLSearchParams(String(witness.query))].sort(), [
      ["cursor", "embedding-test-page"],
      ["limit", "1"],
    ]);
    assert.deepEqual(headerValues(observation, "cache-control"), ["no-store"]);
  },
);
