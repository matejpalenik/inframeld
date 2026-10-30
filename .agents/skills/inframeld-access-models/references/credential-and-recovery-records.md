# Credential evidence and recovery records

<a id="credential-evidence-and-recovery-records"></a>

Alice’s authenticated request carries her principal ID and non-secret evidence of the credential actually checked. Recovery records track independent obligations and credential generations. Neither record freezes permissions for later work.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="access-context-evidence"></a>

<a id="carry-complete-evidence-for-the-authenticated-caller"></a>

### Carry complete evidence for the authenticated caller

Alice's browser context identifies the provider identity verified from her session. Her CLI context carries the exact identity, installation and credential version verified from Hydra. SupportBot's application-key evidence identifies its key without its secret. These are the three alternatives for the required `AccessContextDTO.authentication_evidence` field under [ADR-0073](../../../../docs/adr/ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md). [Record definitions](#authentication-evidence-records) own their fields.

The two implemented human authenticators construct complete contexts. HTTP dependencies and application services pass them unchanged. Authorizers read current facts separately. Both facts readers return the stored principal and exact OAuth binding/version observations. The shared application evaluator checks evidence against the stored principal kind. A kind mismatch is an internal `RuntimeError` before reservation, replay or mutation. It does not change the ordinary denial for a correctly represented application requesting human-only work.

`PrincipalAccessPolicyInput.credential_is_current` has no default. Every producer supplies it explicitly. Browser/application contexts use true because the human OAuth generation check does not apply. That value does not establish browser-session or application-key validity. Production application-key authentication remains unfinished, and authorization tests simulate it with explicit evidence and synthetic key IDs. Add no empty evidence base, marker Protocol or parallel authentication-method enum.

<a id="keep-identity-and-credential-lifecycles-separate"></a>

### Keep identity and credential lifecycles separate

A verified Kratos identity maps through an explicit identity link to the human principal. Kratos owns passwords and browser sessions, so permission records do not contain them. Verify the identity source and subject before using the link. Matching email addresses alone do not join accounts. Hydra adds the accepted human CLI token lifecycle, not another human account or a replacement grant store.

An application key identifies the application principal. The incoming-credential workflow owns its verifier, safe metadata, expiry, revocation, and audience/resource binding. Those records are separate from current grants and group membership. Replacing a key keeps the same principal and permissions. Both usable keys, at most **two per application**, use the account's current authority. Expired and revoked key history is counted separately.

Changing a name or credential does not change the principal. Creating another account with an old display name does not give it the retired account's identity or permissions. Historical attribution follows [retention rules](../../inframeld-knowledge/references/deletion-and-retention.md) and never authorizes new work.

<a id="application-key-record-contract"></a>

<a id="logical-application-key-record-contract"></a>

#### Logical application-key record contract

The [accepted key contract](application-key-contracts.md#application-key-contract) requires the following values. This is a logical record specification for the incoming-credential workflow, not a new migration or implemented table map:

| Value | Meaning and constraint |
| --- | --- |
| Public key ID | Generated UUIDv4 for lookup. Separate from `PrincipalId`. Its presence does not authenticate. |
| Verifier | SHA-256 digest bytes of the complete canonical `ifm_app_<key-UUID>_<secret>` key. Compare in constant time. Never store/replay plaintext or expose the verifier as safe metadata. |
| Account/principal/project bindings | Authoritative association to the exact application and project. Verify current principal/account/project eligibility. Key rotation preserves the account principal. |
| Installation binding | Associate verification with the trusted installation, rather than a caller-selected target label or a key prefix. The [maintenance draft](host-maintenance.md#maintenance-wire) specifies one immutable installation UUID persisted during managed initialization and bound to the operator-controlled installation record. Physical persistence remains an implementation decision. |
| Audience/adapter binding | Authoritative permitted incoming audience/resource/adapter restrictions, checked in addition to the prefix. The issuance input selects supported HTTP/MCP adapter restrictions. The server derives installation/project bindings and current account authority. Exact persistence/wire encoding remains to specify. |
| Safe lifecycle metadata | Issuance attribution/time, expiry and revocation state/time sufficient for the authorized management workflow. Public metadata excludes the secret and digest. |

The secret is 32 cryptographically random bytes encoded as 43 unpadded base64url characters. The default lifetime is 90 days and the maximum 365 days, both operator-configurable. Validate default against maximum. The account has at most two usable keys across audiences. Issuance coordinates the current usable count, full issuer delegation/group-management authority, bindings and audit under the Access write protocol. Revocation and retirement use their independent current human Revoke keys/Delete application account authority and lifecycle checks. They do not require issuance delegation or document-reading authority. Keys use current grants, not a historical issuer ceiling or cached permission snapshot. General UUID identifier constructors retain their existing valid-version/zero-value rules.

<a id="application-key-verification-result"></a>

<a id="temporary-verified-application-key-result"></a>

#### Temporary verified application-key result

SupportBot supplies a complete key. After credential verification, the authentication service needs to know which existing account to load. [ADR-0074](../../../../docs/adr/ADR-0074-separate-application-key-verification-from-local-admission.md) selects a minimal internal application result with exactly two values:

| Value | Application type | Meaning |
| --- | --- | --- |
| Verified key identity | `ApplicationKeyId` | The key whose complete credential and required credential bindings/lifecycle checks passed. |
| Associated application identity | `PrincipalId` | The application principal from that verified stored key/account binding. |

The result carries no secret, verifier digest, account-state snapshot or grants. Its trusted verifier produces it after verification. A caller cannot authenticate merely by supplying the two identifiers, and the record cannot authenticate its own contents.

The authentication service loads the current application account using the returned principal ID and applies eligibility rules. It then constructs the separate `AccessContextDTO` with actor identity and `ApplicationKeyAuthenticationDTO` containing the verified key ID. Existing Access authorizers obtain fresh stored key facts using the key ID in the authentication context. They check its actor binding, expiry and revocation alongside current account, permission and protected-input checks before protected work or replay. For writes, these checks participate in the owning transaction and applicable coordination. This intermediate result establishes neither future credential validity nor continuing authority.

Successful verification produces this record. Credential rejection returns `None` instead of a fabricated or incomplete record. Recognized required verification-dependency availability failures raise `DependencyUnavailableError`. Unexpected failures and cancellation propagate. The [owning verification contract](application-key-contracts.md#verification-results-and-unresolved-currentness) defines service translation and existing HTTP outcomes.

This is an accepted logical result, not an implemented class, public response or persisted record. Its concrete name and method signatures remain implementation work. The accepted [key-boundary resolution](decision-key-currentness.md#approved-resolution) and [job-authority resolution](decision-admitted-work-authority.md#approved-resolution) supply verification inputs, temporal coordination and admitted-job policy. Backend representations remain implementation work. [Current-key authorization ownership](application-keys.md#application-key-current-authorization) is accepted design, not an implemented application-key facts contract. It adds no table, migration or replacement for the [complete authentication evidence](#authentication-evidence-records).

## Durable admission authority

**Accepted logical contract with an implemented ordinary-job subset.** A worker resolves server-owned original operation, principal, installation/scope, fixed action/input meaning and applicable human security generation together with current attempt ownership/fence. It evaluates current account, recovery, action and source facts before protected work. It retains no raw credential, cached grants or boolean authorization bypass. Original admission and later continuation authority remain separate facts. The [approved authority contract](decision-admitted-work-authority.md#approved-resolution) owns expiry, revocation, stopping and trusted system-obligation behavior. This describes the complete accepted meaning, including owner-specific source and system-obligation checks.

The implemented [AdmittedWorkAuthorityDTO](../../../../apps/backend/src/inframeld_backend/access/application/dtos/admitted_work_authority_dto.py) fixes the actor, installation, Project/action scope and original human OAuth generation alongside the job's immutable payload and operation binding. [AdmittedWorkAuthorizationService](../../../../apps/backend/src/inframeld_backend/access/application/services/admitted_work_authorization_service.py) interprets current account, Project, grant, recovery and generation observations without reconstructing an incoming `AccessContextDTO`. Its [reader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_admitted_work_facts_reader.py) coordinates identity, organization and Project state inside the caller's short transaction. A fresh OAuth retry may recover original admission, but does not substitute its newer generation into the old job.

This infrastructure currently admits generation-bound human OAuth and application work. Browser-derived admission is rejected before reservation, job or audit effects, because ordinary browser evidence carries no captured generation. No browser job interface is delivered, and the consent-only pre-verification initializer contract is unchanged. Current source-specific and trusted system-obligation behavior remains with its real owning workflow. [Ordinary execution](../../inframeld-application-contracts/references/jobs-and-recovery.md#implemented-ordinary-job-foundation) owns the implemented lifecycle and qualification limits.

<a id="identity-cleanup-records"></a> <a id="identity-cleanup-records-and-logical-deletion-obligations"></a>

#### Identity-cleanup records and logical deletion obligations

Alice may have no local account when recovery begins. The original operation binds trusted installation/provider/subject and recovery flow to a temporary product block and independent Kratos/Hydra cleanup outcomes. These are operation obligations, not another `PrincipalStatus`, permission snapshot or OAuth-token database. Completed duplicate events dispatch nothing. An unfinished bulk retry or admitted late call may invalidate newer credentials under [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md).

<a id="recovery-delivery-records"></a>

#### Accepted production delivery records

**Accepted logical design with a delivered subset.** [ADR-0085](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) resolves the evidence association and [the completion contract](recovery-completion.md) specifies execution. Keep the existing admission row and domain checklist below. The following supporting records make receipt and unfinished work survive a restart:

| Record | Required retained meaning | Identity and consistency rules |
| --- | --- | --- |
| Evidence receipt | Event type, native flow ID, checked identity/session/source fields, original recovery, server receipt time and original safe acknowledgment. | Unique installation/provider/event-type/native-flow key. Repeats must match immutable meaning. No raw provider object or secret payload. |
| Settings association | Original recovery operation, exact installation/provider/subject, native settings-flow and session IDs, and the receipt establishing the association. | One settings flow has one original binding. A session can map only to the same original operation and identity. New settings flows inherit only that checked session binding. |
| Recovery proof link | New covering recovery and each older unreleased original operation captured when the covering admission is first inserted. | Unique pair, same exact identity scope, immutable directed link. Identity coordination establishes ordering. Duplicate admission adds no links and later recoveries are not included. |
| Cleanup job/progress | One original recovery, first trusted Kratos receipt and eligibility time, independent CLI-grant and remembered-login states, confirmation provenance and current worker lease/ownership token. | One job per original recovery. Each confirmation references its authoritative attempt or a complete linked newer proof. Confirmed progress cannot regress. No new job merely because a callback repeats. |
| Cleanup run | Original job and run ID, automatic or host authorization source, eligibility/authorization time, deadline, twelve-attempt maximum, consumed count, next-attempt time, ended time and safe terminal reason. | At most one unended run per original recovery. An additional run gets a new ID/budget and never edits the old budget. Initial eligibility is recorded once. |
| Cleanup attempt | Run and ordinal, worker/ownership token, claim/dispatch/checkpoint times, independent outcomes for the two fixed provider steps and safe classifications. | Unique run/ordinal. Consume before provider dispatch. A lost worker does not refund it. Only the current owner can advance authoritative progress. |
| Host authorization receipt | Installation, unique operator request ID, canonical intent/target and exact attribution/reason, trusted original identity binding, server authorization time, original safe outcome, and optional resulting run ID/deadline. | Unique installation/request ID across modes. This single immutable receipt is also operator audit history. Equal meaning replays. Different meaning conflicts. Store no-run outcomes too, so later replay cannot authorize another run. |

These are supporting Access records and the accepted shared job lifecycle, not a generic event store, recovery queue or step framework. Migration 0006 implements receipts, associations, proof links and the initial job/run. Migration 0007 adds ownership, attempts, fixed-step observations and complete proof. Migration 0008 adds the immutable host maintenance receipt used for both replay and operator audit. Its request-key uniqueness spans modes. The optional new-run foreign key is deferred, while uniqueness remains immediate. Keep vendor and ORM types outside application/domain contracts. An aggregate does not acquire leases or call providers.

Save admission, its version advancement and links to older obligations in the same coordinated transaction. Save a first trusted password receipt, Kratos proof, job handoff and initial run together before acknowledging. Record each provider confirmation in its own short checkpoint before the next call. No network wait holds those transactions open.

When newer combined proof covers older operations, preserve its receipt and both Hydra confirmations as provenance. Check each explicitly linked checklist's original identity before recording its confirmed cleanup. Record valid cleanup and stop further cleanup attempts even when the account is suspended or retired. Check current eligibility separately before releasing that checklist's block. Do not start an older run merely to consume that proof, overwrite already confirmed evidence, reset its budget, or delete its original history. Mark outstanding old runs ended as `satisfied_by_newer_recovery` and fence fresh dispatch. Admitted remote calls cannot be recalled. The account block is released only through each original checklist's normal local completion.

Run terminal reasons are `cleanup_confirmed`, `attempt_budget_exhausted`, `deadline_exhausted`, `permanent_provider_rejection`, `provider_protocol_error`, `unexpected_error` or `satisfied_by_newer_recovery`. Preserve failed/uncertain step observations independently of those reasons. Ended runs never regain unused attempts on restart. The existing job states remain unchanged. Provider cleanup may succeed while account ineligibility still prevents local release. That is a recorded completion outcome, not permission to repeat cleanup.

Retain versions, original admissions, evidence/proof provenance and run/attempt/authorization history. This slice supplies no pruning or reset policy. Numeric versions and bearer metadata remain governed by their existing authoritative record, not callback input. [Host maintenance](host-maintenance.md#recovery-cleanup-continuation) owns its bounded request and [completion](recovery-completion.md#hydra-cleanup-retry-budget) owns timing and retry calculations.

The implemented [0004 migration](../../../../apps/backend/migrations/versions/0004_identity_recovery.py) creates `identity_recovery_admissions`, mapped by [IdentityRecoveryAdmissionRow](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/identity_recovery_admission_row.py):

| Stored fields | Meaning and constraint |
| --- | --- |
| `operation_id` | Original nonblank operation identity and primary key. |
| `installation_id`, `authority`, `flow_id` | Unique original flow within the trusted installation/provider scope. Installation references authoritative singleton metadata. |
| `subject`, `event_kind` | Original affected provider identity and `recovery` or `password-reset` binding. They are checked on repeat, not included as extra uniqueness dimensions that could admit a conflicting second operation. |
| `kratos_cleanup_state`, `hydra_cleanup_state` | Independent `pending`, `confirmed`, `failed` or `uncertain` outcomes. Both start pending. |
| `admitted_at`, `released_at` | Admission time and explicit release time. A null release keeps the block, even if both provider states are confirmed. The database rejects release unless both states are confirmed. |

There is deliberately no required principal foreign key. Current [admission orchestration](../../../../apps/backend/src/inframeld_backend/access/application/services/identity_recovery_admission_service.py) retains the original event binding. The PostgreSQL writer acquires the identity turn, then any linked organization's exclusive lock before reading current facts and inserting the admission. An unlinked identity can still be recorded without creating a principal. The implemented [identity coordinator](identity-admission-coordination.md) is also available to future first-admission adapters. Complete invitation activation remains unfinished. [Access](eligibility-and-current-authority.md#shared-principal-eligibility) owns adapter deadlines and rollback behavior.

The implemented [IdentityRecovery](../../../../apps/backend/src/inframeld_backend/access/domain/entities/identity_recovery.py) aggregate keeps the cleanup checklist for one installation/provider/flow. It records independent provider outcomes, prevents confirmed cleanup from regressing and requires both confirmations before recording release. The application first checks current local eligibility and observes competing obligations under the required coordination. Under [ADR-0069](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md), each completed eligible checklist releases only its own block. Another unreleased row continues blocking access independently. Completion without a local identity link creates no account. Suspended or retired accounts remain ineligible for automatic release.

The [completion facts](../../../../apps/backend/src/inframeld_backend/access/application/dtos/identity_recovery_completion_facts_dto.py) contain the configured installation, original admission binding, current optional Principal and whether another matching flow is unreleased. The [cleanup result](../../../../apps/backend/src/inframeld_backend/access/application/dtos/identity_recovery_cleanup_result_dto.py) contains the original operation ID, provider states, this flow's release time and that observation of other pending recovery. These are temporary application records, not new tables, durable callback acknowledgments or authorization certificates. [The local completion service](recovery-completion.md#recovery-completion-workflow) owns sequencing and transaction lifetime.

[IdentityRecoveryRepository](../../../../apps/backend/src/inframeld_backend/access/application/protocols/identity_recovery_repository.py) loads and saves existing admissions without provisioning an identity or committing. Its [PostgreSQL adapter](../../../../apps/backend/src/inframeld_backend/access/infrastructure/repositories/postgres_identity_recovery_repository.py) binds exact aggregate instances and immutable value snapshots to one active caller-owned transaction. The original operation ID, event kind and admission time remain persistence metadata outside the domain entity. Loading converts a typed tuple directly into the aggregate and its private tracking record.

An unchanged save performs no writes or freshness check. A changed save updates only cleanup outcomes and release time, conditional on the stored binding and all previously loaded state still matching. For example, if a Hydra worker saves while a Kratos worker still holds the old checklist, the Kratos save raises `ConflictError` instead of erasing Hydra's result. The caller must roll back, discard the repository and reload in a new transaction before deciding what to do next. There is no automatic retry or provider call. Successful saves advance the private snapshot only after persistence succeeds. A failed save or ended transaction makes the repository unusable. These snapshots are infrastructure state, not new database records, recovery versions or authorization evidence. [Repository tests](../../../../apps/backend/tests/integration/access/test_identity_recovery_repository_postgres.py) cover progress, original metadata, release persistence, rollback and concurrent updates.

[Recovery behavior](recovery.md#identity-recovery-cleanup) and [jobs](recovery-completion.md#identity-cleanup) own admission and release rules. [Private callbacks](private-recovery-handoff.md#recovery-callbacks) are separately bounded to 8 KiB, authenticated by a rotatable service secret and deduplicated by their versioned native-flow/event-type contract. That callback contract is not the admission table's unique key, and credential material is not stored in these records. The [private handoff contract](private-recovery-handoff.md#recovery-wire) defines evidence and acknowledgments. Local completion uses the aggregate and repository. Private callback delivery, provider-cleanup orchestration and bounded reconciliation are implemented, with their inspected behavior and qualification limits in the [completion workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion). Bulk Hydra calls have [separate qualification limits](recovery-provider-cleanup.md).

The [bulk revocation capability](recovery-provider-cleanup.md#hydra-cleanup-evidence) consumes an `IdentitySubject` bound by the caller to the original installation/provider identity. The adapter fixes token-grant cleanup to the registered `inframeld-cli` client. Remembered-login cleanup covers that subject across Hydra clients. The original admission already stores the identity binding. No per-login inventory, target snapshot, timestamp cutoff or duplicate OAuth-token database is required by [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md).

The admission row's single Hydra state reflects the two independent durable confirmations required by [the accepted completion proof](recovery-completion.md#completion-proof). The worker saves both before invoking proof-backed local completion. One successful request cannot establish that whole outcome. A typed subject and an empty-scope acknowledgment establish no account ownership or permission. [Fixture-bound provider observations](recovery-provider-cleanup.md#hydra-discovery-evidence) demonstrate why consent listing cannot determine cleanup completeness. The implemented delivery and execution records below preserve attempt ownership, provider checkpoints and proof provenance. The separate [host authorization receipt](host-maintenance.md#recovery-cleanup-continuation) retains additional-run authorization and replay without granting access.

[Issuance-ordering evidence](recovery-provider-cleanup.md#hydra-issuance-evidence) now covers outstanding authorization codes and token responses delivered after cleanup. A login approved afterward can still issue Hydra-active credentials. [Credential versioning](human-cli-credential-lifecycle.md#human-credential-versions) keeps a late grant with an older generation unusable at Inframeld after test-controlled release. The frozen pending-login and code records belong only to the test harness, keep credentials out of representations and create no inventory or persistence requirement. HTTP-ordering evidence does not qualify provider-internal races or authorize recording the aggregate Hydra state as confirmed.

Project deletion similarly binds the original operation to the exact project and initiating principal, reviewed/admitted state, durable block, application/key shutdown obligations and resumable physical cleanup. Retained content-free status may be read by the currently eligible original human under the authoritative operation binding after membership removal. History is not permission to cancel, continue or inspect private contents. The [deletion contract](../../inframeld-knowledge/references/project-deletion.md#project-deletion) owns outcomes and retries. These logical obligations do not select a new public job enum or additional physical tables.

<a id="installation-identity-record"></a>

<a id="installation-identity-and-logical-maintenance-outcomes"></a>

### Installation identity and logical maintenance outcomes

Managed initialization creates one immutable installation UUID before user admission, persisted in authoritative backend metadata and bound into the operator-controlled managed-installation record through verified host access. The same identity survives restart/upgrade and target-label renaming. Factory reset/new installation creates a new identity. Restore follows normal retained-operation reconciliation. The identity is distinct from an Organization, principal, project and mutable URL/target label.

The implemented [0003 migration](../../../../apps/backend/migrations/versions/0003_installation_identity.py) creates and seeds `installation_identity` once. Its fixed primary key `singleton_key = 1` permits at most one row, `installation_id` is a unique UUID, and `created_at` records initialization. [InstallationId](../../../../apps/backend/src/inframeld_backend/shared/domain/value_objects/installation_id.py) uses the runtime UUID-wrapper convention. [PostgresInstallationIdentityReader](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/readers/postgres_installation_identity_reader.py) reads this metadata in its own short session. This code does not by itself qualify the complete host-maintenance workflow or permit readers to silently recreate missing metadata.

A maintenance result binds original operation/mode, installation, verified Kratos authority/subject, exact responsibility and reviewed access revision to its safe assignment outcome. Retain no Hydra proof token. A keyed fingerprint covers stable request meaning and verified subject, excluding replaceable proof bytes. A fresh proof for the same identity can recover the original operation without regranting. [The maintenance wire draft](host-maintenance.md#maintenance-wire) owns proof, fields, errors and scope checks.

<a id="authentication-evidence-records"></a>

### Authentication evidence records

`AccessContextDTO` is a frozen request-local transfer record containing `actor_principal_id: PrincipalId` and required `authentication_evidence`. The evidence is exactly one of these records:

| Record | Required values | Meaning |
| --- | --- | --- |
| `BrowserSessionAuthenticationDTO` | `identity: VerifiedHumanIdentityDTO` | The browser authenticator verified this provider identity. No cookie is retained. |
| `HumanOAuthCredentialBindingDTO` | Verified identity, `InstallationId`, `HumanCredentialVersion` | The exact binding verified from the CLI credential. No token or permission snapshot is retained. |
| `ApplicationKeyAuthenticationDTO` | `key_id: ApplicationKeyId` | The safe key identifier associated with application authentication. No secret is retained. |

`ApplicationKeyId` is a distinct UUID-backed value object using the existing parsed-UUID rule. It neither verifies key ownership nor establishes current validity. These records add no tables, migrations or public response fields. Construction rejects missing or unsupported evidence, but the records do not authenticate themselves. Production application-key authentication remains unfinished. Tests may explicitly simulate it without persisting keys.

The actor is still resolved locally, and current authorization obtains its account kind, status and permissions from current reads. Follow [the request chain](#access-context-evidence) and [ADR-0073](../../../../docs/adr/ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md) for ownership and mismatch behavior.

<a id="human-credential-version-records"></a>

### Human credential version records

The implemented [0005 migration](../../../../apps/backend/migrations/versions/0005_human_credential_versions.py) adds `human_credential_versions`. Its composite primary key is `(installation_id, authority, subject)`. Installation references authoritative installation metadata with restricted deletion. `version` is a positive PostgreSQL BIGINT. No local principal foreign key is required.

Migration backfills existing linked humans and recovery identities at version 1. Unversioned Hydra tokens remain rejected. First consent initialization creates a missing record at 1 without admission or grants. Existing recovery history with missing version state is an integrity failure, never permission to restart at 1. State is retained independently of cleanup-record retention and cannot be reset or downgraded.

Under [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md), initialization and recovery acquire their identity turn before credential-state writes. That transaction-scoped lock needs no existing row and adds no coordination table. Its temporary lifetime is separate from the durable version, which remains authoritative after the lock releases. The three recovery/initialization participants implement this rule. First-admission integration remains future work.

The recovery admission writer advances the version once for each newly inserted original flow in the same transaction as its obligation/block. Duplicate events retain the original operation and generation. Overlapping admissions serialize increments. Overflow, failure and cancellation cannot commit a block without its version change. Completion leaves the version unchanged.

`HumanOAuthCredentialBindingDTO` carries verified provider identity, `InstallationId` and `HumanCredentialVersion`. `HumanCredentialStateDTO` observes authoritative installation, identity, optional initialized version and pending block together. These are typed transfer records, not extra tables or permission certificates. `AccessContextDTO` requires one of the [authentication evidence records](#authentication-evidence-records). OAuth evidence retains this binding so authorization can compare it again. The shared eligibility input carries the current comparison result, not a cached permission.

`HumanOAuthCredentialFactsDTO` is an attempt-local read projection with required `binding_matches_actor: bool` and `current_version: HumanCredentialVersion | None`. The match covers the current installation and the presented provider identity's link to the actor. A missing version stays absent. Both project facts DTOs carry the stored principal/actor, pending-recovery flag and optional OAuth facts instead of an evaluated eligibility input. OAuth evidence always has a facts record, while browser/application evidence has none. The shared application evaluator constructs `PrincipalAccessPolicyInput` from these observations and the unchanged authenticated context. [Component ownership](eligibility-and-current-authority.md#credential-query-and-policy-boundaries) keeps SQL construction, boundary conversion and validity decisions separate.

[Access behavior](human-cli-credential-lifecycle.md#human-credential-versions) owns issuance, current checks and errors. [ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md) owns the API guarantee and its provider limits.

<a id="principal-eligibility-inputs"></a>

<a id="temporary-principal-eligibility-inputs"></a>

### Temporary principal eligibility inputs

Alice may remain an active principal while an unreleased recovery obligation blocks her product access. Keep those facts separate in persistence. [ADR-0064](../../../../docs/adr/ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md) selects a common policy input that brings the observed Principal and pending-recovery fact together for one authorization attempt.

[`PrincipalAccessPolicyInput`](../../../../apps/backend/src/inframeld_backend/access/domain/policy_inputs/principal_access_policy_input.py) is an implemented frozen, slotted domain input. Authorization services construct it from stored facts and authentication evidence, then operation-specific policies consume it. It is not a new table, aggregate root, Principal status or stored allow/deny flag. It is not cached in `AccessContextDTO`, which retains the authenticated principal ID and required non-secret authentication evidence.

The data loader must establish the exact principal, organization and authoritative installation context. Recovery is matched through stored authority/subject links, with any unreleased matching obligation counting as pending. A later local link must respect an obligation recorded before principal admission. Missing installation metadata is a dependency failure, not proof that there is no block. Project membership, action grants and caller-kind restrictions remain additional facts and rules.

These observations do not authorize a later transaction or retry. Authorization operations load current facts again under the applicable coordination contract. [Access](eligibility-and-current-authority.md#shared-principal-eligibility) owns behavior and verification evidence, and [application structure](architecture.md#shared-access-eligibility) owns component responsibilities. The shared input and policy are implemented runtime components and add no persisted records.

### Implemented delivery persistence

[Migration 0006](../../../../apps/backend/migrations/versions/0006_identity_recovery_delivery.py) adds native evidence receipts, immutable session/settings bindings, explicit newer-to-older proof links, and the original cleanup job/run. Composite foreign keys preserve the original installation/provider/subject binding. Native event uniqueness preserves acknowledgment identity. One active run per original operation preserves the first twelve-attempt/one-hour budget.

No evidence, association or cleanup success is invented for existing admissions. Receipts retain allowlisted typed columns rather than arbitrary provider bodies. The job has separate pending CLI-grant and remembered-login outcomes. The application constructs the initial budget from the original password receipt timestamp. Persistence explicitly stores its twelve-attempt limit and one-hour deadline, keeping database defaults and constraints as safeguards. A later settings event cannot replace that initial receipt or extend the budget. Consumed attempts start at zero. Migration 0007 implements worker claims, attempts and result provenance. Host-run authorization uses migration 0008's receipt and preserves this original handoff. [Private delivery](private-recovery-handoff.md#implemented-private-delivery) owns the implemented flow.

### Implemented recovery execution records

[Migration 0007](../../../../apps/backend/migrations/versions/0007_identity_recovery_cleanup_execution.py) preserves existing admissions, receipts, jobs and budgets. Its compact Alembic revision is `0007_recovery_cleanup_execution`, fitting the existing revision-column limit. It backfills no provider success.

The job keeps its current attempt, worker, lease and ownership token, plus immutable first-confirmation pointers. Retained attempts have a unique run ordinal. Fixed-step records admit only CLI-grant revocation and remembered-login deletion, with allowlisted outcome/disposition/category fields and safe parsed retry delays. Scoped foreign keys prevent borrowing another original operation's attempt or evidence. Database checks retain complete ownership fields, valid outcome combinations and bounded attempt numbers.

Complete proof binds each original to one source recovery, its password receipt and both confirmed step records. It also records independently pending local completion and propagation. Coverage preserves an existing proof rather than overwriting provenance. An older original can receive proof without gaining a fabricated password receipt or cleanup job. A checked ineligible outcome stops automatic local polling, while explicit future eligible workflows retain their existing release rules. No record resets credential versions or grants access by itself.

Each original coverage link records a one-time reconciliation checkpoint. Existing complete proof does not skip a newly eligible original-release check. For example, a new recovery can recheck an older cleanup-complete block after a separate authorized account restoration. Preserve the older proof while recording that the newer link was processed in the same transaction as the checklist check. An ineligible result still ends that link's automatic work, without continuously polling for restoration.
