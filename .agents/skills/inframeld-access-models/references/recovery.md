# Recovery blocks, cleanup and completion

<a id="follow-recovery-admission"></a>

## Choose a focused reading task

- For provider cleanup and uncertainty, read [Recovery provider cleanup](recovery-provider-cleanup.md).
- For local completion and independent block release, read [Recovery completion](recovery-completion.md).

## Follow recovery admission

1. Establish trusted provider/installation identity and original recovery-flow evidence. Do not accept caller-supplied identity or a fresh settings query parameter as original-flow proof.
2. Take [the identity turn](identity-admission-coordination.md) around recovery admission/completion and credential initialization before required organization/project locks. These participants are implemented. Future first-admission integration remains unfinished, and no turn spans provider verification or cleanup.
3. Record the recovery obligation. For a linked human, admission takes the conflicting exclusive organization lock so grant writes cannot ignore a newly committed block. Its fixed five-second database deadline includes waits and leaves rollback to the caller. An identity without a local link may still receive an obligation without local provisioning.
4. Advance the human CLI credential version once atomically for a new recovery. Duplicate delivery and block release do not reset it. Current authentication/authorization rejects old binding evidence even after the temporary block is later released.
5. Load the `IdentityRecovery` aggregate to record supported checklist transitions through its specific repository. Original admission metadata stays with infrastructure. Neither loading nor saving authenticates provider evidence or establishes release eligibility.
6. Record trusted outcomes and release only the eligible original flow through the local completion workflow. Other blocks remain authoritative. Completion before local admission provisions nothing.

An aggregate is the domain object responsible for cohesive state transitions. Here it protects Alice's cleanup checklist. Its repository preserves transaction-bound snapshots and conditional-save conflict detection. Keep exact instances within one caller transaction.

If a changed save conflicts, roll back and load current state before another decision. Do not automatically repeat provider calls. An unchanged save performs no writes or freshness checks.

<a id="implementation-status-and-limits"></a>

## Implementation status and limits

The aggregate, repository, admission and local completion service are implemented foundations recorded in the guides.

Private native callbacks, bounded provider cleanup and proof-backed per-checklist completion are implemented. Protected host continuation, first-local-admission integration and packaged deployment remain separate work. Old-version rejection supplies the accepted late-issuance guarantee, not a promise that Hydra can never issue another credential. Standalone bulk-provider tests, password-gap observations and test-only token hooks do not qualify those missing pieces.

The [Hydra retry budget](recovery-completion.md#hydra-cleanup-retry-budget) is accepted under [ADR-0083](../../../../docs/adr/ADR-0083-bound-hydra-recovery-cleanup-retries.md). [ADR-0084](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) permits a fresh explicit host authorization for [another bounded run](recovery-completion.md#operator-cleanup-continuation) on the same unfinished recovery. Prior history and confirmed progress remain intact. The automatic budget is implemented. Additional host-authorized runs remain unfinished. Neither exhaustion nor operator authorization releases a recovery block.

[The accepted failure policy](recovery-completion.md#hydra-cleanup-failure-handling) retries recoverable provider failures and uncertain bulk outcomes within budget. A known permanent rejection ends that run early while retaining the block and progress. After fixing the cause, the host operator may authorize continuation without waiting for the ended run's hour to expire. [The exact mapping](recovery-completion.md#hydra-cleanup-failure-handling) is now accepted, while the richer adapter result and durable orchestration remain unimplemented.

Recovery never clears suspension, recreates removed permissions or lets an older completion release a newer independent block. Preserve ordinary account eligibility, current authorization on replay and product-specific visibility ordering.

<a id="identity-recovery-cleanup"></a>

<a id="block-product-access-until-verified-recovery-cleanup-finishes"></a>

### Block product access until verified recovery cleanup finishes

Alice can recover her password without having been suspended. At the authenticated server-side boundary, trusted flow-bound evidence of verified identity recovery/reset durably admits one cleanup operation and temporarily blocks her product access. Evidence of the verified reset is distinct from confirmation that both providers have finished session/grant cleanup. The Kratos recovery and password-setting screens remain usable. An anonymous request for a recovery email, a browser redirect or an OAuth callback is not proof of recovery completion and cannot trigger revocation.

Track Kratos-session cleanup and affected Hydra-grant cleanup independently. A confirmed success from one provider does not establish the other outcome. Failure or uncertainty keeps the product block in place while bounded reconciliation continues the original operation. Provider calls happen outside a database transaction. The operation must distinguish the legitimate new recovery session from sessions to invalidate.

| Current local account state | After both required cleanup outcomes are confirmed |
| --- | --- |
| Active admitted human | Release only this operation's block. Current admission, other recovery blocks and grants still apply. |
| No local identity link | Release this finished obligation without creating an account or granting access. |
| Suspended or retired local account | Do not release automatically or change account status. Suspension still needs a separately authorized Restore users operation and its security review. |
| Another recovery is unreleased | It continues blocking product access. This completed eligible flow may release only its own block. |

Deduplicate trusted completion using its original flow-bound event identity. A duplicate completed event returns its recorded outcome without initiating another provider call. An unfinished bulk retry or already-dispatched call may invalidate newer CLI credentials under [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md). Neither cleanup completion nor restoration recreates explicitly removed memberships or grants. Keep callback evidence bounded and credential-free: do not include session cookies/tokens in callback payloads or audit. The temporary block is an operation obligation, not a newly selected `Principal` status or permission snapshot. [ADR-0058](../../../../docs/adr/ADR-0058-block-product-access-during-identity-recovery-cleanup.md) records the cleanup block, refined by [ADR-0069](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md) for overlapping recoveries and completion before local admission. [Durable cleanup](recovery-completion.md#identity-cleanup) and [logical records](credential-and-recovery-records.md#identity-cleanup-records) own the related contracts.

**Accepted hook-based integration:** [ADR-0081](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) selects the recovery webhook for admission after code verification, followed by a password-settings webhook after password persistence and native `revoke_active_sessions`. The latter supplies Kratos evidence for the original recovery before independent durable Hydra cleanup. The admitted block protects the password-setting gap. [The private handoff](private-recovery-handoff.md#native-hook-evidence) owns the sequence and each callback's meaning.

A session ID in a pre-save callback does not prove password replacement or native cleanup. Neither a generic webhook response nor a completed password form proves both providers finished cleanup. [Provider observations](recovery-provider-cleanup.md#kratos-password-reset-evidence) distinguish inspected capability and earlier probes from the implemented private delivery and worker tests. [The private callback contract](private-recovery-handoff.md#recovery-callbacks) retains its dedicated rotatable service secret, versioned allowlisted body limited to 8 KiB and stable native-flow/event-type deduplication. [ADR-0085](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) settles the association, failure recovery and completion contract. Private native delivery is implemented as described in [the handoff](private-recovery-handoff.md#implemented-private-delivery). Durable Hydra execution and proof-backed release are implemented in the dedicated worker.

<a id="authorization-failure-scenarios"></a>

## Authorization failure scenarios

| Situation | Required outcome |
| --- | --- |
| Appoint a manager through normal administration, creation, or recovery. | Membership and management are saved together with the revision and audit. A manager without membership is invalid. |
| Suspend the only manager, then recover the group. | Reading and administration stop immediately. Recovery gives both assignments to an eligible replacement and keeps the compromised account blocked. |
| Exercise login, logout, recovery, MFA, CSRF, disabled identities, and provider or session-check outages. | Unverifiable identity is denied. Restoring an account follows the deliberate recovery process. |
| Delete a Document, application, or project. | Each operation respects its own limits, cleanup, and handover rules. |

| Situation | Required outcome |
| --- | --- |
| Verified recovery finishes Kratos cleanup while Hydra cleanup is uncertain. | Product access stays blocked and reconciliation uses the original operation. An unfinished bulk attempt may invalidate newer CLI credentials. A completed duplicate initiates no new cleanup. |
| Project deletion succeeds but Alice loses the response and later her membership. | Recover the original operation under the narrow content-free status rule. Keep failed shutdown/cleanup blocked without recreating the project. |

| Situation | Required outcome |
| --- | --- |
| Kratos cleanup succeeds but Hydra cleanup is uncertain. | Keep product blocked and reconcile the original operation. An unfinished bulk attempt may revoke newer CLI credentials, but a completed duplicate initiates no new cleanup. |
| Private complete arrives before admission, or binds another identity to the flow. | Safe 409. No new obligation/block release. Reconcile the original trusted admission. |
| A sole manager is suspended and provider cleanup fails. | Suspension succeeds without handover. Access stays blocked and its original obligation persists. Restore cannot bypass incomplete cleanup or security review. |

<a id="pending-decisions-for-dependent-implementation"></a>

## Accepted contracts and remaining delivery

[PD-ACCESS-03 is resolved](decision-recovery-production-completion.md). Its acceptance matrix separates trusted callback delivery (#243), durable Hydra cleanup/release (#244) and protected operator continuation (#245). The private callback path is implemented. Durable cleanup/release are implemented. Protected host continuation remains unfinished. A newer recovery may provide combined proof for explicitly linked older checklists under [the reconciliation rule](private-recovery-handoff.md#recover-original-evidence), but cannot bypass their individual release checks.

First-account coordination is settled under [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md), resolving [PD-ACCESS-04](decision-recovery-first-admission.md). Follow [the accepted identity workflow](identity-admission-coordination.md) when implementing its participating database operations. First-admission integration remains separate from the implemented recovery worker.

<a id="sources-and-rationale"></a>

## Sources and rationale

- [Recovery cleanup](#identity-recovery-cleanup), [completion workflow](recovery-completion.md#recovery-completion-workflow), [credential versions](human-cli-credential-lifecycle.md#human-credential-versions) and [cleanup records](credential-and-recovery-records.md#identity-cleanup-records).
- [Bulk Hydra evidence](recovery-provider-cleanup.md#hydra-cleanup-evidence), [discovery observations](recovery-provider-cleanup.md#hydra-discovery-evidence), [issuance ordering](recovery-provider-cleanup.md#hydra-issuance-evidence), [password-reset observations](recovery-provider-cleanup.md#kratos-password-reset-evidence) and [reconciliation](recovery-completion.md#identity-cleanup).
- [ADR-0058](../../../../docs/adr/ADR-0058-block-product-access-during-identity-recovery-cleanup.md), [ADR-0069](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md), [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md), [ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md) and [ADR-0081](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md).
- [Private recovery handoff](private-recovery-handoff.md#recovery-wire) is implemented privately and supplies no public recovery bypass.
