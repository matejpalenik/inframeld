import assert from "node:assert/strict";
import {
  assertDispatch,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import { sdkTest, type CaseCall } from "../../src/conformance/cases.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const groupIds = [
  "00000000-0000-4000-8000-000000000007",
  "00000000-0000-4000-8000-000000000008",
];
const filename = "règlement + &.pdf";
const authorization = "Bearer sdk-human";
const pdf = Buffer.concat([Buffer.from("%PDF-1.7\n"), Buffer.from([255, 0])]);
const original = {
  operation: "uploadDocument",
  path: { project_id: projectId },
  query: { groupIds, filename },
  headers: {
    Authorization: authorization,
    "Idempotency-Key": "sdk-pdf-original",
  },
  body: { fileBase64: pdf.toString("base64") },
  timeout: 2000,
} satisfies CaseCall;

function assertUpload(
  witness: Record<string, JsonValue>,
  bytes: Buffer,
  key: string,
): void {
  assertDispatch(witness, "POST", `/v1/projects/${projectId}/documents`);
  assert.equal(witness.rawBodyBase64, bytes.toString("base64"));
  const query = new URLSearchParams(String(witness.query));
  assert.deepEqual(query.getAll("groupIds"), groupIds);
  assert.deepEqual(query.getAll("filename"), [filename]);
  assert.equal(witness.authorization, authorization);
  const headers = witness.headers;
  assert.ok(headers && typeof headers === "object" && !Array.isArray(headers));
  assert.equal(headers["content-type"], "application/pdf");
  assert.equal(headers["idempotency-key"], key);
}

const result = {
  operationId: "sdk-pdf-original",
  projectId,
  documentId: "00000000-0000-4000-8000-000000000034",
  documentVersionId: "00000000-0000-4000-8000-000000000035",
  idempotencyExpiresAt: "2030-01-01T00:00:00Z",
};

sdkTest(
  {
    id: "upload-document-original-replay",
    operation: "uploadDocument",
    outcome: "success",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    for (const { observation, witness } of await sequence([
      original,
      original,
    ])) {
      assertUpload(witness, pdf, "sdk-pdf-original");
      assert.deepEqual(assertSuccess(observation, 201), result);
      assert.deepEqual(headerValues(observation, "cache-control"), [
        "no-store",
      ]);
    }
  },
);

sdkTest(
  {
    id: "upload-document-changed-bytes",
    operation: "uploadDocument",
    outcome: "failure",
    expectedCalls: 2,
  },
  async ({ sequence }) => {
    const changed = Buffer.concat([pdf, Buffer.from([1])]);
    const [first, second] = await sequence([
      original,
      { ...original, body: { fileBase64: changed.toString("base64") } },
    ]);
    assert.ok(first && second);
    assert.deepEqual(assertSuccess(first.observation, 201), result);
    assertUpload(first.witness, pdf, "sdk-pdf-original");
    assertUpload(second.witness, changed, "sdk-pdf-original");
    const { observation } = second;
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 409);
    assert.ok(
      ["generated-model", "generated-schema"].includes(observation.validation),
    );
    const body = observation.body;
    assert.ok(body && typeof body === "object" && !Array.isArray(body));
    assert.equal(body.code, "idempotency_key_reused");
  },
);

sdkTest(
  {
    id: "upload-document-legacy-null-deadline",
    operation: "uploadDocument",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      ...original,
      headers: { ...original.headers, "Idempotency-Key": "sdk-pdf-legacy" },
    });
    assertUpload(witness, pdf, "sdk-pdf-legacy");
    assert.deepEqual(assertSuccess(observation, 201), {
      ...result,
      operationId: "sdk-pdf-legacy",
      idempotencyExpiresAt: null,
    });
  },
);
