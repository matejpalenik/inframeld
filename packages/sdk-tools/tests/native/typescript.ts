import type {
  ContractFixturePayload as Payload,
  ProblemDetails,
} from "../../fixtures/typescript/generated/types.gen.js";
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

import type { ProjectUseOnlyGrantResponse as Grant } from "../../../sdk-typescript/generated/types.gen.js";
const noGrantAuthority: Pick<Grant, "canGrant"> = { canGrant: false };
// @ts-expect-error This response cannot grant authority to its recipient.
const inventedAuthority: Pick<Grant, "canGrant"> = { canGrant: true };
void [noGrantAuthority, inventedAuthority];

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
