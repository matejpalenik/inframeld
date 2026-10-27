# Admit humans and activate invitations

Alice invites Bob into Support and intends to make him a member of SupportKnowledge. Bob proves his own identity. The invitation describes intended access, but cannot promise that Alice will still be authorized when he activates it.

## Identity, admission and assignments

Kratos verifies a human identity. Access links its trusted provider authority and subject to a stable local principal. Local admission permits entry into the installation. Project membership, group membership and exact action grants are separate relationships. Matching email alone never joins identities or grants rights.

An invitation is a revocable, single-use intent, not an identity proof or an unrestricted invitation role. It can admit Bob and carry explicit assignments. It does not automatically make him an installation administrator. Private starter provisioning and the first-administrator host claim have their own [first-use workflow](../../inframeld-architecture/references/first-use-and-private-defaults.md) and [fixed initial grants](actions-and-initial-grants.md).

<a id="invitations"></a> <a id="single-use-invitations-with-current-authority"></a>

## Follow issuance, preview and activation

1. **Alice requests exact effects.** Access checks her current `admit-users` authority and every requested membership, group-management and exact-action delegation authority. A document-action assignment may use its existing group-manager delegation alternative. Ordinary grants to already-admitted humans remain a separate operation.
2. **Access saves the intended scope.** Save the issuer, installation/Organization, exact assignments, affected Project bindings, expiry and original operation. Check reviewed revisions under the required locks. Do not retain the plaintext token. Its authorized first delivery is the only opportunity to obtain it.
3. **Bob signs in and previews.** The narrow preview uses his verified Kratos browser cookie, CSRF and protected invitation token before local product admission. It shows only authoritative intended labels and expiry. It creates no principal, assignments, reservation or promise of future success.
4. **Bob explicitly activates.** In the accepted target, take [Bob's identity turn](identity-admission-coordination.md) before any required organization/project locks, then recheck the valid unused invitation, current issuer eligibility/authority and Bob's actual state. Require existing eligible Project membership or an explicit membership intent for every affected Project. Group-manager intent adds group membership, not Project membership. Reject a missing prerequisite rather than silently adding it.
5. **Commit one local result.** Bind the verified subject to the legitimate principal, consume the invitation and save all guarded assignments, audit and original outcome together. Concurrent consumption cannot assign twice. External Ory onboarding and local activation retain separate outcomes.

The preview/activation exception permits only these narrow admission operations. It cannot bypass ordinary product authorization, restore a suspended human or release recovery blocks. Do not invoke a dependency that already requires an admitted local principal to perform first admission.

## Failures, retries and changed authority

| Situation | Required outcome |
| --- | --- |
| Alice loses a promised authority before new activation | Fail current checks atomically. Do not silently reduce or widen the assignment set. |
| A reviewed Project changes before issuance commits | Conflict without a partial invitation. Reviewed state is not continuing permission. |
| Bob lacks prerequisite Project membership | Require an explicit membership intent or existing eligible membership. No implicit relationship or partial consumption. |
| Preview succeeds, then state changes | Activation runs its own current checks and can fail. |
| Recovery commits before a valid new activation | Safe 409 without account creation, invitation consumption or assignments. The recipient can explicitly try again after recovery. |
| Activation commits before recovery | Recovery sees the new identity link and blocks that account through its original obligation. |
| The token is invalid, expired, revoked or used for a new activation | Safe 404 without revealing private scope. Stale/ineligible intended effects use safe 409. |
| Issuance succeeds but delivery is lost | Recover safe metadata with the secret absent. Do not issue another token as an automatic retry. |
| Activation commits but its response is lost | Find the original completed operation before applying new-consumption preconditions. |
| Alice leaves or the invitation expires after completed activation | The same currently verified, eligible Bob may recover the retained safe original result. It cannot grant again or restore removed rights. |
| Another identity or a different key tries to consume again | Deny or conflict. No second assignment. |

Revoking the invitation prevents new consumption. It does not remove assignments made by a completed activation. Existing credential expiry, revocation, suspension and recovery checks still govern replay. Knowing an invitation or operation ID is not permission to inspect unrelated history.

<a id="invitation-records"></a> <a id="logical-invitation-intent-and-activation"></a>

## Safe retained intent

Retain the original identity, issuer, target bindings, intended effects, expiry/revocation/consumption facts and original activation outcome. Store a token digest separately from safe metadata. Keep original operation identity and the verified recipient binding when the response is lost. These logical responsibilities do not require a table or repository per noun.

## Implementation status and reading routes

The invitation lifecycle and documented transport draft are accepted at their stated status. They do not establish implemented invitation routes, a production account UI or qualified concurrent first admission.

For exact inputs, route symbols, limits and response alternatives, read [Invitation contracts](invitation-contracts.md). For a target's exact fields, read [Grant targets](grant-target-contract.md). For existing membership or delegation changes, read [Grant administration](grant-administration.md) and [Memberships and handover](memberships-groups-and-handover.md).

The [identity-coordination workflow](identity-admission-coordination.md) is accepted under [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md), resolving [PD-ACCESS-04](decision-recovery-first-admission.md). Its shared lock and recovery/initialization participants are implemented. Complete invitation activation remains unimplemented and must reuse that boundary. [ADR-0062](../../../../docs/adr/ADR-0062-activate-invitations-under-current-issuer-authority.md) retains the invitation rationale.
