import assert from "node:assert/strict";
import type {
  ContractFixturePayload as Payload,
  ProblemDetails,
} from "../../fixtures/typescript/generated/types.gen.js";
import {
  zHumanAdmissionRequest,
  zMyOrganizationAccessResponse,
  zProjectCreationRequest,
  zProjectMembershipRequest,
  zProjectMetadataUpdateRequest,
} from "../../../sdk-typescript/generated/zod.gen.js";

const revisionIdentifier = "00000000-0000-4000-8000-000000000001";
const revisionModels = [
  [
    "expectedAccessRevision",
    zHumanAdmissionRequest,
    { identityId: revisionIdentifier },
  ],
  [
    "expectedAccessRevision",
    zProjectCreationRequest,
    {
      organizationId: revisionIdentifier,
      name: "support",
      displayName: "Support",
    },
  ],
  ["expectedAccessRevision", zProjectMembershipRequest, {}],
  [
    "expectedMetadataRevision",
    zProjectMetadataUpdateRequest,
    { name: "support" },
  ],
  [
    "accessRevision",
    zMyOrganizationAccessResponse,
    {
      organizationId: revisionIdentifier,
      principalId: revisionIdentifier,
      grants: [],
    },
  ],
] as const;
for (const [field, schema, otherFields] of revisionModels) {
  for (const revision of [0, Number.MAX_SAFE_INTEGER]) {
    assert.equal(
      schema.safeParse({ ...otherFields, [field]: revision }).success,
      true,
    );
    assert.deepEqual(schema.parse({ ...otherFields, [field]: revision }), {
      ...otherFields,
      [field]: revision,
    });
  }
  for (const revision of [
    -1,
    Number.MAX_SAFE_INTEGER + 1,
    1n,
    true,
    "1",
    1.5,
  ]) {
    assert.equal(
      schema.safeParse({ ...otherFields, [field]: revision }).success,
      false,
    );
  }
}

const valid: Payload = {
  required_name: "valid",
  required_nullable: null,
  score: 0.5,
  choice: 7,
};
const alternate: Payload = { ...valid, choice: "seven" };
// @ts-expect-error The nullable field is still required.
const absent: Payload = { required_name: "valid", score: 0.5, choice: 7 };
// @ts-expect-error The scalar union accepts neither booleans nor arbitrary objects.
const wrongChoice: Payload = { ...valid, choice: true };
const problem: ProblemDetails = {
  type: "https://problems.test/future",
  title: "Future",
  detail: "Reviewed error",
  status: 422,
  code: "future_error_code",
  requestId: "00000000-0000-4000-8000-000000000099",
  errors: [
    {
      location: "body",
      path: ["items", 0],
      code: "out_of_range",
      message: "Out of range",
    },
  ],
};
void [valid, alternate, absent, wrongChoice, problem];

import type {
  ProjectActionGrantRemovalResponse,
  ProjectActionGrantResponse,
} from "../../../sdk-typescript/generated/types.gen.js";
const removed: Pick<ProjectActionGrantRemovalResponse, "removed"> = {
  removed: true,
};
const inventedRemoval: Pick<ProjectActionGrantRemovalResponse, "removed"> = {
  // @ts-expect-error A removal acknowledgement cannot report false.
  removed: false,
};
const useOnly: Pick<ProjectActionGrantResponse, "canGrant"> = {
  canGrant: false,
};
const delegating: Pick<ProjectActionGrantResponse, "canGrant"> = {
  canGrant: true,
};
void [removed, inventedRemoval, useOnly, delegating];

import type {
  Options as SessionOptions,
  GetCurrentSessionData,
} from "@inframeld/sdk";
const forbiddenResponseContract: SessionOptions<GetCurrentSessionData> = {
  // @ts-expect-error Generated response selection is not a caller-facing option.
  responseContract: {},
};
void forbiddenResponseContract;

import type { SdkFailure } from "@inframeld/sdk";
function inspectFailure(error: SdkFailure<ProblemDetails>): string {
  // @ts-expect-error A network or decoding failure has no validated problem body.
  const unsafe = error.body.title;
  void unsafe;
  return error.kind === "api" ? error.body.title : error.message;
}
void inspectFailure;

import type { ContractFixtureMediaResponses } from "../../fixtures/typescript/generated/types.gen.js";
const ordinaryRepresentation: ContractFixtureMediaResponses[200] = {
  value: "ready",
};
const vendorRepresentation: ContractFixtureMediaResponses[200] = {
  jobId: "job-123",
};
// @ts-expect-error Every declared representation requires its own model fields.
const missingRepresentation: ContractFixtureMediaResponses[200] = {};
void [ordinaryRepresentation, vendorRepresentation, missingRepresentation];

import type { ContractFixtureVariantsResponses } from "../../fixtures/typescript/generated/types.gen.js";
const fallbackRepresentation: ContractFixtureVariantsResponses["default"] = {
  jobId: "job-123",
};
void fallbackRepresentation;

const forbiddenPathEncoding: SessionOptions<GetCurrentSessionData> = {
  // @ts-expect-error Path encoding is fixed by generated operation metadata.
  encodedPathParams: [],
};
void forbiddenPathEncoding;

import type {
  OriginalOperationLookupRequest,
  AcceptedOperationLookupResponse,
} from "@inframeld/sdk";
// @ts-expect-error An original authority guard is required even when other context is retained.
const missingLookupGuard: Pick<
  OriginalOperationLookupRequest,
  "expectedAuthority"
> = {};
const unknownLookupJob: Pick<AcceptedOperationLookupResponse, "jobReference"> =
  { jobReference: "unknown" };
const knownLookupJob: Pick<AcceptedOperationLookupResponse, "jobReference"> = {
  jobReference: { jobId: "00000000-0000-4000-8000-000000000008" },
};
const guessedLookupJob: Pick<AcceptedOperationLookupResponse, "jobReference"> =
  {
    // @ts-expect-error A known reference requires its typed identifier object.
    jobReference: "known",
  };
void [missingLookupGuard, unknownLookupJob, knownLookupJob, guessedLookupJob];

import type {
  ProjectMetadataUpdateRequest,
  ProjectMetadataResponse,
} from "@inframeld/sdk";
const selectorOnlyMetadata: ProjectMetadataUpdateRequest = {
  expectedMetadataRevision: 0,
  name: "production",
};
const unicodeMetadata: ProjectMetadataUpdateRequest = {
  expectedMetadataRevision: 0,
  displayName: "🧭".repeat(128),
};
const nullSelectorMetadata: Pick<ProjectMetadataResponse, "name"> = {
  name: null,
};
// @ts-expect-error A nullable selector must still be present in a read response.
const absentSelectorMetadata: Pick<ProjectMetadataResponse, "name"> = {};
const clearedMetadata: ProjectMetadataUpdateRequest = {
  expectedMetadataRevision: 0,
  // @ts-expect-error An omitted replacement differs from an explicit null replacement.
  displayName: null,
};
void [
  selectorOnlyMetadata,
  unicodeMetadata,
  nullSelectorMetadata,
  absentSelectorMetadata,
  clearedMetadata,
];
