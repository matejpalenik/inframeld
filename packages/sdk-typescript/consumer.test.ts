import type {
  ContractFixturePayload as Payload,
  ProblemDetails,
} from "./generated/fixtures/types.gen.js";
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

import type { ProjectUseOnlyGrantResponse as Grant } from "./generated/production/types.gen.js";
const noGrantAuthority: Pick<Grant, "canGrant"> = { canGrant: false };
// @ts-expect-error This response cannot grant authority to its recipient.
const inventedAuthority: Pick<Grant, "canGrant"> = { canGrant: true };
void [noGrantAuthority, inventedAuthority];
