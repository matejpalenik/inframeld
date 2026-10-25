# Invitation requests, responses and restrictions

Alice invites Bob into Support. These design contracts describe the exact requested intent and safe responses. Read the invitation workflow for why issuance, preview, new activation and completed replay have different checks.

> **Status:** Documented version 1 transport draft with accepted behavior. These are not implemented Pydantic models or generated OpenAPI operations.

<a id="invitations-and-key-routes"></a>

## Invitation routes

| Method and route | Operation ID | Named input / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/invitations` | `issueInvitation` | `InvitationIssueRequest` / `InvitationIssueResponse` | Human administration. Current `admit-users` and all promised assignment authorities. 201. |
| `POST /v1/invitations/{invitation_id}/revoke` | `revokeInvitation` | `InvitationRevocationRequest`: `expectedAccessRevision` / `InvitationRevocationResponse` | Human administration. Original issuer currently eligible with `admit-users`, or current can-use-and-grant on `admit-users` for the Organization. 200. No authority over completed assignments follows. |
| `POST /v1/invitations/preview` | `previewInvitation` | `InvitationPreviewRequest` / `InvitationPreviewResponse` | Invitation preview profile. 200 for current safe intended scope. No consumption, reservation or admission. |
| `POST /v1/invitations/activate` | `activateInvitation` | `InvitationActivationRequest` / `InvitationActivationResponse` | Invitation activation profile. 200 after guarded consumption/admission/assignments. |

## Typed design blocks

**Design notation, not production implementation.** The following blocks replace prose field lists in this reference. They preserve the documented wire names. `GrantTarget` is defined once in [the exact target contract](grant-target-contract.md). No importable module is implied. An annotation, `Never`, or a comment does not perform input validation. In these blocks UUID and datetime denote the corresponding serialized JSON strings.

```python
from datetime import datetime
from typing import Literal, Never, NotRequired, TypedDict
from uuid import UUID

# GrantTarget is defined in grant-target-contract.md.
# UUID/datetime denote JSON UUID strings and UTC RFC 3339 timestamps.

class ProjectMembershipIntent(TypedDict):
    kind: Literal["project-membership"]
    projectId: UUID

class GroupMembershipIntent(TypedDict):
    kind: Literal["group-membership"]
    projectId: UUID
    accessGroupId: UUID

class GroupManagerIntent(TypedDict):
    kind: Literal["group-manager"]
    projectId: UUID
    accessGroupId: UUID
    # Includes ordinary group membership, not Project membership.

class ActionGrantIntent(TypedDict):
    kind: Literal["action-grant"]
    target: GrantTarget
    actionId: str  # Existing fixed catalogue value for this exact target.
    canGrant: bool

class AdmissionOnlyIntent(TypedDict):
    kind: Literal["admission-only"]
    # Must be the only assignment when selected.

type InvitationAssignment = (
    ProjectMembershipIntent | GroupMembershipIntent | GroupManagerIntent
    | ActionGrantIntent | AdmissionOnlyIntent
)

class ProjectAccessRevision(TypedDict):
    projectId: UUID
    accessRevision: int  # Strict nonnegative signed-BIGINT range.

class InvitationIssueRequest(TypedDict):
    organizationId: UUID
    assignments: list[InvitationAssignment]  # 1–100 unique intended effects.
    expectedAccessRevision: int
    expectedProjectAccessRevisions: list[ProjectAccessRevision]
    # Unique Project IDs, every affected Project exactly once, at most 100.
    # Empty for admission-only or Organization-only intent.
    expiresInSeconds: NotRequired[int]  # Strict positive configured-bound lifetime.

class InvitationIssueResult(TypedDict):
    operationId: str
    accessRevision: int
    idempotencyExpiresAt: datetime
    invitationId: UUID
    organizationId: UUID
    assignments: list[InvitationAssignment]
    expiresAt: datetime

class InvitationFirstDelivery(InvitationIssueResult):
    secretAvailable: Literal[True]
    invitationToken: str  # Show once, never a URL or identity proof.

class InvitationIssuanceReplay(InvitationIssueResult):
    secretAvailable: Literal[False]
    invitationToken: NotRequired[Never]  # Omit the field, do not send null.

type InvitationIssueResponse = InvitationFirstDelivery | InvitationIssuanceReplay

class InvitationRevocationRequest(TypedDict):
    expectedAccessRevision: int

class InvitationRevocationResponse(TypedDict):
    operationId: str
    accessRevision: int
    idempotencyExpiresAt: datetime
    invitationId: UUID
    organizationId: UUID
    revoked: Literal[True]

class InvitationPreviewRequest(TypedDict):
    invitationToken: str  # Protected JSON body, never query/path/log input.

class InvitationScopeResponse(TypedDict):
    target: GrantTarget
    displayName: str  # Authoritative presentation label, not a selector.

class InvitationPreviewResponse(TypedDict):
    invitationId: UUID
    organizationId: UUID
    assignments: list[InvitationAssignment]
    expiresAt: datetime
    scopes: list[InvitationScopeResponse]  # Deduplicated, at most 201 items.

class InvitationActivationRequest(TypedDict):
    invitationToken: str

class InvitationActivationResponse(TypedDict):
    operationId: str
    invitationId: UUID
    organizationId: UUID
    principalId: UUID
    organizationAccessRevision: int
    projectAccessRevisions: list[ProjectAccessRevision]
    idempotencyExpiresAt: datetime
```

`InvitationIssueResult`, `InvitationFirstDelivery` and `InvitationIssuanceReplay` are teaching names for the response alternatives. The documented transport symbol remains `InvitationIssueResponse`. They add no endpoint or application record. All new objects reject unknown fields. [Access input bounds](grant-contracts.md#shared-wire-field-bounds-and-owner-specific-handoffs) retain strict revisions, text, body parsing and header rules.

## Validation that needs current state

1. Bind every target to this installation/Organization and its authoritative affected Project. Validate the action and intended recipient kind through the fixed catalogue. Assignments apply to the activating human, never a caller-selected application.
2. Require 1–100 unique assignment identities. Reject duplicate grants, two levels for one intended grant and incompatible mixtures. `admission-only` has no other fields and is the sole item when used.
3. Group/action effects require the actual recipient's current eligible Project membership or an explicit Project-membership intent for that Project. Group-manager intent includes group membership, but never silently adds Project membership. Missing prerequisites return safe 409 with no consumption or partial assignment.
4. At issuance, compare every affected Project revision under the normal Organization-then-sorted-Project locks. The reviewed revision list covers every affected Project exactly, has no duplicate Project and contains at most 100 entries. It is empty for admission-only/Organization-only effects.
5. At new activation, recheck the saved effects against current issuer eligibility, every required authority and actual recipient state. Do not use issuance revisions as continuing authority or silently widen/reduce the promised set.

Issuance requires current `admit-users` plus each intended membership, group-management and exact-action delegation authority. The group-manager alternative applies only to the existing document-action assignments on that group. There is no broader membership-only invitation capability. Ordinary direct assignment to admitted users stays a separate operation.

## Secrets, lifetimes and safe examples

Generate 32 cryptographically random token bytes and encode them as 43 unpadded base64url characters. Verify a SHA-256 digest with constant-time comparison. Retain safe metadata and the digest, never replayable plaintext. Delivery, errors, audit, logs and traces must not expose the token outside its first authorized response.

The configurable lifetime defaults to seven days and is capped at thirty days. The default cannot exceed the configured maximum. A requested shorter lifetime must be a strict positive whole number within that maximum. Check arithmetic and overflow before effects.

A valid effect set can explicitly add Project membership and then ordinary membership in SupportKnowledge. A group-only intent for Bob, who lacks Project membership and has no explicit membership intent, cannot activate. A preview may describe that intended scope but cannot guarantee later success.

For response loss, `secretAvailable: false` with the token field absent is valid safe issuance recovery. Returning the original token again, returning it as null, or issuing another invitation merely because the CLI timed out violates the selected contract.

## A complete issuance example

This illustrative JSON is a complete request body for an invitation that explicitly supplies both prerequisites. Its UUIDs and revisions are examples, not existing resources. The request still needs the selected human credential, required CSRF when cookie-authenticated and original `Idempotency-Key`.

```json
{
  "organizationId": "00000000-0000-0000-0000-000000000001",
  "assignments": [
    {
      "kind": "project-membership",
      "projectId": "00000000-0000-0000-0000-000000000002"
    },
    {
      "kind": "group-membership",
      "projectId": "00000000-0000-0000-0000-000000000002",
      "accessGroupId": "00000000-0000-0000-0000-000000000003"
    }
  ],
  "expectedAccessRevision": 7,
  "expectedProjectAccessRevisions": [
    {
      "projectId": "00000000-0000-0000-0000-000000000002",
      "accessRevision": 12
    }
  ],
  "expiresInSeconds": 3600
}
```

Access loads the real Organization/Project/group relationships and Alice's current authority. A UUID with valid spelling can still name the wrong scope. If Bob lacks Project membership, deleting the first assignment from this example makes new activation fail its prerequisite check. A group intent cannot repair that omission silently.

## Preview, activation and completed replay

Preview uses the verified Kratos cookie and cookie-write CSRF boundary before local admission. Its protected token is in a bounded JSON body. Although the method is POST, this is a read: no `Idempotency-Key`, reservation, consumption, account admission or assignment. Return authoritative baseline Organization, affected Projects and intended target labels only, deduplicated within 201 scope items. Do not expose issuer inventory, provider details or document content.

New preview/activation uses safe 404 for invalid, expired, revoked or already-used tokens. Stale/ineligible intent uses safe 409. Current browser identity and recovery restrictions apply even before a local identity link exists. Linked suspension restrictions also remain authoritative. Activation cannot restore a human or release a recovery block.

Under the accepted [identity-coordination rule](identity-admission-coordination.md), new activation takes the recipient's identity turn before organization/project locks and then reads current state. A valid new activation blocked by recovery returns safe 409 without creating an account, consuming the invitation or applying assignments. The invitation can be retried after recovery if its ordinary validity and authority checks still pass. Lock-budget exhaustion instead follows the unavailable outcome with rollback. This design does not change invalid-token 404 handling or completed-operation replay.

Before local admission, bind the activation reservation to the independently verified configured Ory authority/subject, exact invitation and route/key. Preserve the resulting stable principal binding after commit. Consumption, exact assignments, audit and original outcome commit together.

Find original completed activation before treating consumed state as a fresh request. Replay requires the same currently verified recipient, eligible local state and authority to read the safe outcome. A different key or identity cannot consume again. New-consumption expiry, unused state and current issuer assignment authority are not reapplied as if an original completed operation were new. Replay cannot switch recipient, recreate removed rights or bypass an expired/revoked credential. Revocation of an invitation does not undo completed assignments.

## Sources and unresolved portions

[The human workflow](admission-and-invitations.md), [initial-grant catalogue](actions-and-initial-grants.md), [target variants](grant-target-contract.md) and [grant transport bounds](grant-contracts.md) own their respective details. [ADR-0062](../../../../docs/adr/ADR-0062-activate-invitations-under-current-issuer-authority.md) records the accepted invitation boundary.

[PD-ACCESS-04](decision-recovery-first-admission.md) is resolved by [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md). Implement new activation against [the accepted coordination workflow](identity-admission-coordination.md). Documenting these draft shapes does not implement the identity lock, account UI or trusted provider integration, or establish concurrent-admission test evidence.
