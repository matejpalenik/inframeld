# Admit humans and activate invitations

In the accepted workflow, Alice admits Bob to the installation without creating his starter resources. An invitation can additionally describe intended memberships and grants, but cannot promise that Alice will still be authorized when Bob activates it.

## Identity, admission and assignments

Kratos verifies a human identity. Access links its trusted provider authority and subject to a stable local principal. Local admission permits entry into the installation. Project membership, group membership and exact action grants are separate relationships. Matching email alone never joins identities or grants rights.

An invitation is a revocable, single-use intent, not an identity proof or an unrestricted invitation role. It can admit Bob and carry explicit assignments. It does not automatically make him an installation administrator. Private starter provisioning and the first-administrator host claim have their own [first-use workflow](../../inframeld-architecture/references/first-use-and-private-defaults.md) and [fixed initial grants](actions-and-initial-grants.md).

<a id="ordinary-human-admission"></a>

## Admit a human without provisioning starters

**Accepted design:** [ADR-0126](../../../../docs/adr/ADR-0126-separate-human-admission-from-private-starter-provisioning.md), approved on 2026-11-03, separates ordinary human admission from required private starter provisioning. Ordinary human admission is implemented through HTTP and the generated application clients as a supporting component.

Alice must be a currently eligible human with permission to use `admit-users` for the installation's Organization. Authorize Alice's current use of `admit-users` in a preliminary transaction, then close it before the private Kratos lookup for Bob. Access then verifies Bob's real Kratos identity and its exact trusted provider authority and subject. A typed email, an OAuth consent result or a caller-supplied local identity cannot replace that verification. All provider I/O stays outside local database transactions.

In the final transaction, take [Bob's identity turn](identity-admission-coordination.md), then an exclusive Organization turn. Reread current authority, recovery, admission, exact identity-binding and Organization Access-revision facts before saving. Commit Bob's principal/link, local admission, required audit and original result together. A conflict or failed check leaves no partial admission or duplicate identity. Admission neither creates starter resources nor assigns implicit `create-projects` authority. It cannot restore a suspended human or clear a recovery block.

Only fresh `201` new-principal admission, after the reviewed Organization revision and current eligibility checks, may initialize an absent [human credential version](credential-and-recovery-records.md#human-credential-version-records) at 1 when no history exists. Preserve an existing generation. Missing version state with history fails closed. A fresh `200` already-admitted result changes no business or credential state and does not advance the Organization Access revision. It commits exactly one required no-change audit with the original no-change outcome and completion.

Before replaying a completed business receipt, recheck both Alice's current `admit-users` authority and Bob's exact current provider identity, local-principal binding and recovery admissibility. Current suspension, provider inactivation or a pending/unreleased recovery block rejects business-receipt replay. Completed recovery history alone does not deny replay. This differs from [generic original-operation metadata lookup](../../inframeld-application-contracts/references/operation-recovery-contracts.md#original-request-lookup), which retains its own disclosure contract.

If the response is lost, return the original business result only after those current checks. Replay never initializes credential state, restores admission or rights, provisions or repairs resources, or adds another audit. A completed admission remains completed if later starter provisioning fails.

The first-use journey still requires the separate [private-starter operation](../../inframeld-architecture/references/first-use-and-private-defaults.md#make-provisioning-safe-to-repeat). That operation retains its principal/purpose identity, atomic ordinary resources and explicit creator grants. Its completion and deliberate-removal state govern later setup. Admission alone is not setup readiness. The first-administrator host claim and invitation activation retain their existing authority and outcomes.

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

Ordinary admission uses `POST /v1/organizations/{organization_id}/human-admissions` (`admitHuman`). The [browser guide](../../../../apps/docs/src/app/guides/admit-human/page.mdx) and [native API reference](../../../../apps/docs/src/app/api-reference/projects-and-access/page.mdx#admit-an-existing-human) describe its consumer path. Invitation issuance, preview and activation remain separate accepted design, not implemented by this component. Full #27 still includes the unadmitted-human proof producer, private starters and usable first setup. Human acceptance remains unperformed under [#185](https://github.com/matejpalenik/inframeld/issues/185).

For exact inputs, route symbols, limits and response alternatives, read [Invitation contracts](invitation-contracts.md). For a target's exact fields, read [Grant targets](grant-target-contract.md). For existing membership or delegation changes, read [Grant administration](grant-administration.md) and [Memberships and handover](memberships-groups-and-handover.md).

The [identity-coordination workflow](identity-admission-coordination.md) is accepted under [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md), resolving [PD-ACCESS-04](decision-recovery-first-admission.md). Its shared lock and recovery/initialization participants are implemented. Complete invitation activation remains unimplemented and must reuse that boundary. [ADR-0062](../../../../docs/adr/ADR-0062-activate-invitations-under-current-issuer-authority.md) retains the invitation rationale.
