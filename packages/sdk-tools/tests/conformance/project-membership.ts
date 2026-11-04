import assert from "node:assert/strict";
import { sdkTest, type CaseCall } from "../../src/conformance/cases.ts";
import {
  assertJsonBody,
  assertSuccess,
  headerValues,
} from "../../src/conformance/assertions.ts";
import type { JsonValue } from "../../src/conformance/protocol.ts";

const projectId = "00000000-0000-4000-8000-000000000003";
const recipient = "00000000-0000-4000-8000-000000000004";
const unchangedRecipient = "00000000-0000-4000-8000-000000000005";
const headers = {
  Authorization: "Bearer sdk-human",
  "Idempotency-Key": "sdk-membership-key",
};
const operations = [
  { kind: "add", operation: "addProjectMember", field: "member" },
  { kind: "remove", operation: "removeProjectMember", field: "removed" },
] as const;
type Kind = (typeof operations)[number]["kind"];

function input(
  kind: Kind,
  principalId: string,
  credentials: Record<string, string>,
  revision = 7,
): CaseCall {
  return {
    operation: kind === "add" ? "addProjectMember" : "removeProjectMember",
    path: { project_id: projectId, principal_id: principalId },
    headers: credentials,
    ...(kind === "add"
      ? { body: { expectedAccessRevision: revision } }
      : { query: { expectedAccessRevision: revision } }),
    timeout: 2000,
  };
}

function receipt(kind: Kind, principalId: string, changed: boolean) {
  return {
    operationId: `sdk-project-membership-${kind}`,
    idempotencyExpiresAt: "2030-01-01T00:00:00Z",
    projectId,
    principalId,
    accessRevision: changed ? 8 : 7,
    changed,
    [kind === "add" ? "member" : "removed"]: true,
  };
}

function assertRequest(witness: Record<string, JsonValue>, kind: Kind) {
  assert.ok(
    witness.headers &&
      typeof witness.headers === "object" &&
      !Array.isArray(witness.headers),
  );
  assert.equal(witness.headers["idempotency-key"], "sdk-membership-key");
  if (kind === "add") {
    assertJsonBody(witness, { expectedAccessRevision: 7 });
    assert.equal(witness.query, "");
  } else {
    assert.equal(witness.rawBodyBase64, "");
    assert.deepEqual(
      [...new URLSearchParams(String(witness.query))],
      [["expectedAccessRevision", "7"]],
    );
  }
}

for (const { kind, operation, field } of operations) {
  for (const credential of ["bearer", "cookie"] as const)
    for (const changed of [true, false])
      sdkTest(
        {
          id: `project-member-${kind}-${credential}${changed ? "" : "-unchanged"}`,
          operation,
          outcome: "success",
        },
        async ({ call, origin }) => {
          const principalId = changed ? recipient : unchangedRecipient;
          const credentials =
            credential === "bearer"
              ? headers
              : {
                  Cookie: "ory_kratos_session=sdk-cookie",
                  Origin: origin,
                  "X-Inframeld-CSRF": "1",
                  "Idempotency-Key": "sdk-membership-key",
                };
          const { observation, witness } = await call(
            input(kind, principalId, credentials),
          );
          assert.deepEqual(
            assertSuccess(observation, kind === "add" && changed ? 201 : 200),
            receipt(kind, principalId, changed),
          );
          assertRequest(witness, kind);
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
      id: `project-member-${kind}-original-wire-result`,
      operation,
      outcome: "success",
      expectedCalls: 2,
    },
    async ({ sequence }) => {
      const request = input(kind, recipient, headers);
      const results = await sequence([request, request]);
      assert.equal(results.length, 2);
      for (const { observation, witness } of results) {
        assert.deepEqual(
          assertSuccess(observation, kind === "add" ? 201 : 200),
          receipt(kind, recipient, true),
        );
        assertRequest(witness, kind);
      }
    },
  );

  for (const failure of ["cookie-csrf", "forbidden", "stale"] as const)
    sdkTest(
      {
        id: `project-member-${kind}-${failure}`,
        operation,
        outcome: "failure",
      },
      async ({ call }) => {
        const credentials =
          failure === "cookie-csrf"
            ? {
                Cookie: "ory_kratos_session=sdk-cookie",
                "Idempotency-Key": "sdk-membership-key",
              }
            : failure === "forbidden"
              ? { ...headers, Authorization: "Bearer sdk-denied" }
              : headers;
        const { observation } = await call(
          input(kind, recipient, credentials, failure === "stale" ? 6 : 7),
        );
        assert.equal(observation.kind, "sdk-error");
        assert.equal(observation.status, failure === "stale" ? 409 : 403);
        assert.notEqual(observation.validation, "none");
        assert.ok(
          observation.body &&
            typeof observation.body === "object" &&
            !Array.isArray(observation.body),
        );
        assert.equal(
          observation.body.code,
          failure === "stale" ? "stale_revision" : "access_denied",
        );
        assert.deepEqual(headerValues(observation, "cache-control"), [
          "no-store",
        ]);
      },
    );

  sdkTest(
    {
      id: `project-member-${kind}-rejects-false-outcome`,
      operation,
      outcome: "failure",
    },
    async ({ call }) => {
      const { observation, witness } = await call({
        ...input(kind, recipient, headers),
        fault: {
          kind: "json",
          status: kind === "add" ? 201 : 200,
          body: { ...receipt(kind, recipient, true), [field]: false },
        },
      });
      assert.equal(observation.kind, "sdk-error");
      assertRequest(witness, kind);
    },
  );
}

sdkTest(
  {
    id: "project-member-remove-needs-replacement",
    operation: "removeProjectMember",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation, witness } = await call(
      input("remove", "00000000-0000-4000-8000-000000000006", headers),
    );
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 409);
    assert.notEqual(observation.validation, "none");
    assertRequest(witness, "remove");
  },
);
