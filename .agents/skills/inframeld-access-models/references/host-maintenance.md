# Host-authorized bootstrap and repair

<a id="host-authorized-bootstrap-and-repair"></a>

Alice is the first administrator, or Support has lost its last eligible grantor. A verified host operator can repair one reviewed responsibility. A normal product credential does not supply host authority.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="the-server-operator-can-recover-a-stranded-responsibility"></a>

### The server operator can recover a stranded responsibility

An **in-app administrator** has only their assigned permissions. There is no unrestricted UI superadministrator or special ability to read documents.

The **server operator** controls the host, Compose setup, databases, storage, secrets, and backups. Application permissions cannot hide plaintext from someone with that level of infrastructure access. The same person may also use the application, but their ordinary session still follows its assigned permissions.

Prefer help from an already authorized peer or recovery of the legitimate account. If neither is possible, privileged operator maintenance may appoint a verified replacement for the exact responsibility that has no remaining administrator:

| Missing responsibility | What recovery assigns |
| --- | --- |
| A group's manager | Membership and management of that group, saved together. This includes its document access, but no unrelated group's access. |
| Someone who can grant a particular action | Can use and grant for that action on that exact resource. No wider permissions are added. |

The compromised account stays blocked. Recovery records the operator, reason, changed permissions, and the access change number together with the change. It does not give the operator ordinary document-reading permissions or let an in-app administrator take over private groups.

For bootstrap and stranded-authority repair, the accepted boundary is a narrow one-shot maintenance command executed inside the verified managed backend using the operator's existing host/container-exec authority. Supply bounded protected input, an expected immutable installation identity, independently verified Ory identity and the exact reviewed request state. Recovery-cleanup continuation below reuses host authority without recipient proof or reviewed-run input. An ordinary bearer token, email address, target label or Docker context name is not operator authority or sufficient installation proof. Remote host maintenance remains separate from ordinary remote CLI login. Do not expose a public claim/maintenance API, shared claim password or backend Docker socket.

First-administrator setup commits the verified identity link, admission, four explicit organization grants and audit together. Replaying the same original claim returns that result without recreating removed grants. A competing identity fails. For repair, the replacement must already be an active admitted verified human. Recheck under the applicable organization/project locks that the exact responsibility is still stranded and the reviewed revision is current. A stale review fails without partial assignments. Save the operator reason, before/after revisions and audit with the exact membership/management or use-and-grant repair. The audit explains the action but cannot prevent misuse by a trusted host operator. The [maintenance contract](#maintenance) selects `inframeld-maintenance`, one protected versioned JSON request limited to 64 KiB, independent verification of the candidate's current Ory session/identity, exact reviewed intent and safe output. Host execution authorizes repair. The session proof identifies its recipient. The [version 1 bootstrap/repair modes](#maintenance-wire) consume a transient Hydra human access token as protected recipient identity proof. This does not establish a supported CLI producer for an unadmitted human. Private introspection and current Kratos identity checks precede local reads. Host execution supplies authority. First bootstrap may verify before local admission, while repair requires an active admitted eligible recipient. The bootstrap consumer requires an already initialized authoritative installation identity. It does not initialize or replace that identity.

Deliver suspension/restoration and scoped operator maintenance as explicit capabilities, separate from ordinary membership/grant administration. The immediate local block, external Kratos/Hydra cleanup and deliberate restoration have separate recorded outcomes: cleanup failure cannot lift the block. A retry inspects or continues the original cleanup. It never restores access merely to make another provider request. Operator maintenance uses a privileged host boundary, not an unrestricted token or hidden bypass in ordinary CLI authentication. The [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) assigns these workflows and their specification/security qualification prerequisites. Recovery continuation and the [narrow Project metadata repair consumer](#project-metadata-authority-repair) are implemented. The private first-administrator bootstrap consumer is implemented. Group repair and other action-repair variants remain design-only and unsupported.

<a id="first-administrator-bootstrap-consumer"></a>

## Bootstrap the first administrator through the private consumer

The [backend maintenance command](../../../../apps/backend/src/inframeld_backend/bootstrap/maintenance.py) now accepts `mode: bootstrap-first-administrator` through the protected version 1 stdin contract below. The installed `inframeld-maintenance` entry point and `python -m inframeld_backend.maintenance` take no command arguments. This is a private executable consumer, not a public claim endpoint or a complete first-setup workflow.

The [composition](../../../../apps/backend/src/inframeld_backend/bootstrap/first_administrator_bootstrap_composition.py) uses raw Hydra access-token verification and current Kratos identity verification before database startup checks, identity/claim reads or receipt replay. It does not use an ordinary authenticator that requires an admitted principal. Verify the expected installation and Kratos identity, then apply current credential-generation, history, recovery-block and eligibility checks inside the coordinated database stage. Provider waits remain outside SQL. Existing provider/total verification deadlines and the five-second database-stage budget are unchanged.

The [facts reader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_first_administrator_bootstrap_facts_reader.py) takes the identity turn, locks the existing installation singleton, then takes any existing Organization coordination. Fresh reads follow the waits. Only a pristine installation with no prior claim or business graph can be claimed. Legitimate pre-admission credential/recovery metadata is not itself a business graph, but cannot bypass its current generation/history/block checks. Ambiguous legacy business state fails closed. Missing grants never prove that an installation is unclaimed.

The fresh claim atomically saves one Organization, active human principal, identity link, four explicit Organization can-use-and-grant assignments, required audit/revision and the original durable receipt. The actions are `admit-users`, `suspend-users`, `restore-users` and `create-projects`. The implementation uses Organization label `Inframeld` and original revision `0` advancing to `1`. These are fixed consumer values, not a human naming policy or hidden administrator permission. It creates no Project, starter group, collection or Pipeline and makes no model call.

The [service](../../../../apps/backend/src/inframeld_backend/access/application/services/first_administrator_bootstrap_service.py) verifies current same-person proof and eligibility before replay. The same original operation meaning returns its original receipt without regranting, renaming or advancing the revision. A different meaning or maintenance mode cannot reuse that host operation ID. Missing/interrupted output remains uncertain, so preserve the original operation instead of starting another claim.

The required migration is [revision `0016_first_administrator`](../../../../apps/backend/migrations/versions/0016_first_administrator_bootstrap.py), whose parent is `0015_artifact_allocation`. Startup and this consumer do not migrate. [PostgreSQL](../../../../apps/backend/tests/integration/access/test_first_administrator_bootstrap_postgres.py), [native provider/command](../../../../apps/backend/tests/integration/access/test_native_first_administrator_bootstrap.py) and [migration](../../../../apps/backend/tests/integration/postgres/test_first_administrator_bootstrap_migration_postgres.py) cases are authored but unrun locally. They remain required CI qualification, not results established by reading this reference.

A usable first installation still needs a supported unadmitted-human proof producer and the broader setup/starter work in #27. The repair-only helper owned by #160 requires an already-admitted session and cannot produce bootstrap proof. Provider fixtures may stage proof for engineering tests, but are not an operator token-minting or administrative-approval recipe. First-install human acceptance remains [#185](https://github.com/matejpalenik/inframeld/issues/185), distinct from [#298](https://github.com/matejpalenik/inframeld/issues/298)'s already-admitted metadata-repair journey.

<a id="project-metadata-authority-repair"></a>

## Repair only stranded Project metadata authority

**Implemented narrow repair consumer.** [The Project metadata decision](decision-project-metadata-authority.md) selects the first repair subset for #120. Alice already belongs to Support, but no active eligible human can grant its new `edit-project-metadata` action. The operator may establish exactly that responsibility. Creator history, another action or an unrelated administrator cannot authorize it.

Use the protected version 1 envelope below with `mode: repair-stranded-authority`, `responsibility.kind: action-grantor`, `responsibility.target.kind: project`, its exact `projectId`, and literal `actionId: edit-project-metadata`. #120 must reject other repair targets/actions and group-manager repair as unsupported. General repair and bootstrap remain separate design work. This subset neither introduces a public endpoint nor expands ordinary product-token authority.

Verify the authoritative installation ID against the independently controlled managed-backend binding. Missing/mismatched identity fails without initialization. Privately introspect the transient Hydra proof and load current Kratos identity facts, matching `expectedIdentityId`. Keep provider waits outside SQL transactions. Host/container execution authorizes repair, while the token identifies only its recipient. Require an existing active admitted human and current membership in the target Project.

Take the existing identity/recovery turn and Organization/Project coordination, then recheck recipient eligibility/membership, active Project state, expected Project Access revision and the exact responsibility’s stranded state. An eligible human grantor that appeared since review prevents repair. Missing or unavailable facts cannot prove absence. Atomically save only this use-and-grant assignment, the Access revision increment, operator attribution/reason, before/after revisions, required audit and the original safe receipt. Failed audit/commit or a competing repair leaves no partial assignment.

Use the same installation/operator `operationId` namespace as recovery continuation. Retain a keyed fingerprint of verified identity, mode, exact target/action, original reviewed revision and request meaning, excluding replaceable proof bytes. Every attempt verifies current proof and recipient eligibility. Look up a matching completed receipt before fresh-write stranded/revision checks. It returns the original safe result, including after this grant was later removed, without regranting. Changed identity, mode or meaning conflicts. After lost output, reuse the original operation ID and meaning with valid same-identity proof.

Persist a typed repair payload alongside the common immutable receipt. Preserve cross-mode request uniqueness, recovery-continuation replay and its real recovery binding. Do not fabricate a recovery operation, run or deadline for repair. General grant/revocation HTTP remains #28. #120 must honor current grants/removals without claiming that broader interface exists.

Before delivery, qualify private Ory proof verification, strict/oversized/duplicate input rejection, stale/unknown state, concurrent repairs, audit rollback, refreshed-proof replay, cross-mode conflicts and replay after grant removal. The schema below remains a design view and is not runtime acceptance evidence.

<a id="recovery-cleanup-continuation"></a>

## Continue unfinished recovery cleanup

**Implemented recovery mode.** Alice's cleanup run ends, the operator fixes Hydra and explicitly authorizes another run of the same original recovery. [ADR-0084](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) permits unlimited such authorizations over its lifetime. Each run still has twelve attempts within one hour. An early permanent rejection does not require waiting for the old deadline.

Use the backend-only `inframeld-maintenance` command with one protected stdin JSON object, at most **64 KiB (65,536 bytes)**. Host/container-exec authority authorizes this mode independently of any ordinary product session. It does not depend on delivering first-administrator or stranded-authority repair. There is no network maintenance API or shared claim password.

| Required input | Value |
| --- | --- |
| `schemaVersion` | Integer token `1`. |
| `mode` | `resume-recovery-cleanup`. |
| `expectedInstallationId` | The independently operator-controlled installation UUID. |
| `operationId` | Unique nonblank operator request ID, at most 128 characters, reused after response loss. |
| `recoveryOperationId` | The nonblank original stored recovery operation ID. This differs from the operator request ID. |
| `operatorLabel` | Nonblank accountable attribution, at most 128 characters. |
| `reason` | Nonblank explanation, at most 512 characters. |

No reviewed-run ID, access revision, identity assertion, recipient proof, cookie, token, password or scope override is accepted. Reject extra/duplicate fields and a second JSON value. The [design schema](../../../../contracts/design/access/maintenance-v1.schema.json) describes this mode separately from bootstrap/repair.

Within short database work, verify authoritative installation metadata and load the original stored provider/identity binding. Take the identity turn before required organization/project and job/run coordination, then reread current state. Save one immutable maintenance receipt with the planned outcome before changing runs. This receipt supplies both replay and host-operator audit history. It stores the exact validated attribution/reason, original binding, server authorization time and optional new run/deadline. Save it and any run changes in one transaction. No provider call occurs in the command transaction.

Deduplicate by installation and operator `operationId` across maintenance modes. Equal canonical mode/target/attribution/reason meaning recovers the original outcome before applying new-run checks. Different meaning returns `idempotency_key_reused`. Immediate request-key uniqueness arbitrates concurrent requests, including different recovery targets. Only the optional new-run foreign key is deferred until commit. Persist successful no-run outcomes too, so their replay cannot later authorize work. There is no operator-reviewed-run precondition.

| Current state | Result for a fresh host request |
| --- | --- |
| Eligible unfinished cleanup and no active run | Create a separate run, preserving previous budgets/history and confirmed progress. |
| Another run is active | Conflict `cleanup_run_active`, no parallel run. An expired lease alone does not end a budget. A live final attempt is still active. Settle genuine terminal/deadline/attempt exhaustion under coordination before replacement, fencing ownership while preserving dispatched uncertainty. |
| Trusted Kratos completion evidence is missing | Reject `recovery_evidence_missing`. The operator cannot manufacture it. |
| Recovery already released | Return `already-completed`, no new run. |
| Both Hydra steps are confirmed but release remains pending | Return `cleanup-confirmed` with the observed release state, no provider work. Normal local eligibility still governs release. |
| Original recovery does not exist | Reject `recovery_not_found`, do not initialize an account or recovery. |

A successful stdout JSON object contains `schemaVersion: 1`, `mode`, operator `operationId`, `installationId`, `recoveryOperationId`, `outcome` and observed `released`. `outcome: cleanup-authorized` additionally contains its original `runId` and UTC `deadline`. The two no-run outcomes omit those fields. Covered originals need no job of their own. Valid saved confirmations can restore missing complete proof for normal reconciliation. An already checked ineligible proof is not requeued by maintenance. A repeated accepted request returns its original output, not a claim about current access or a renewed deadline.

Controlled errors use the existing safe `MaintenanceErrorResponse`, with the parsed operator request ID when available and no reflected input. Exit 0 means verified authorization/replayed/no-run success, 2 invalid input, and 1 operational failure. Reuse `installation_mismatch`, `idempotency_key_reused`, `dependency_unavailable` and `unexpected_error`, plus the three mode-specific codes above. A missing or interrupted response is unknown: repeat the same request ID, not a new authorization.

Authorizing a run supplies neither provider success nor access. It cannot restart completed cleanup, repeat confirmed steps, clear another obligation, restore a principal or permissions, or advance/reset a credential version. Already-admitted calls can still finish late. [Completion](recovery-completion.md#operator-cleanup-continuation) owns execution and [records](credential-and-recovery-records.md#recovery-delivery-records) own retained authorizations and budgets.

<a id="maintenance"></a>

<a id="one-shot-maintenance-through-protected-stdin"></a>

## One-shot maintenance through protected stdin

The accepted backend-only command name is `inframeld-maintenance`, with separate bootstrap, exact stranded-authority repair and [recovery-cleanup continuation](#recovery-cleanup-continuation) intents. The table below describes bootstrap/repair. Recovery continuation has its own fields above. Read one JSON request from protected stdin, limited to **64 KiB (65,536 bytes)**. Recovery continuation, [first-administrator bootstrap](#first-administrator-bootstrap-consumer) and the narrow [Project metadata repair consumer](#project-metadata-authority-repair) are implemented. Other repair variants below remain accepted design and are unsupported.

| Required input | Meaning |
| --- | --- |
| `schemaVersion` | Explicit input-contract version. |
| `expectedInstallationId` | Installation identity from operator-controlled installation state, compared with authoritative persistent backend identity. |
| Original `operationId` | Identify the original claim/repair for safe replay. |
| Operator attribution and reason | Safe accountable description of the host action. |
| Exact responsibility/target and reviewed revision | Bootstrap's fixed Organization assignments, or the one reviewed stranded relationship/action being repaired. |
| Candidate identity and current Ory session proof | Independently verify the candidate's current session and trusted Ory identity, not a caller-supplied email or subject assertion. |

For bootstrap/repair, host/container execution authorizes maintenance. The candidate's proof identifies the human who receives the exact assignments. Bootstrap may admit a verified human not yet locally admitted. Repair requires an already active admitted human. Consume proof secrets only through protected input and verification. Never put them in argv, environment, logs, audit or replay records. Safe output contains exact outcome, IDs and revisions. The [version 1 maintenance contract](#maintenance-wire) distinguishes the implemented bootstrap/metadata-repair inputs from broader repair design. The authoritative installation identity must already exist. Runtime qualification remains required.

Existing host/container-exec authority admits maintenance. Bootstrap/repair verify installation identity against authoritative managed state and recipient identity evidence through the trusted Ory boundary. Do not trust a caller's target label, email, Docker context or product bearer. Recheck stranded state and revisions under the normal organization/project coordination. Save only the reviewed replacement assignments and audit together. No network maintenance API, shared claim password or backend Docker socket is introduced.

<a id="maintenance-wire"></a>

<a id="version-1-host-maintenance-input-and-proof"></a>

## Version 1 bootstrap/repair input and proof

**Implemented bootstrap and restricted repair, with broader repair still design-only.** Bootstrap accepts its nine-field request with no `responsibility`. The repair consumer accepts only the [Project metadata subset](#project-metadata-authority-repair). The broader envelope below does not make group repair or other action-repair variants runnable. The accepted design uses the backend-only `inframeld-maintenance` command once with a versioned JSON object through protected stdin, maximum 64 KiB, with `schemaVersion: 1` and `mode: bootstrap-first-administrator` or `repair-stranded-authority`. Reject unknown fields, duplicate object keys and a second JSON value. No secret argument, environment variable, browser-cookie extraction, refresh token or ID token is supported.

| Field | Required value |
| --- | --- |
| `schemaVersion`, `mode` | Version 1 and one of the two modes above. |
| `expectedInstallationId` | UUID from the independently operator-controlled installation record. |
| `operationId` | Original nonblank opaque host operation ID, maximum 128 characters. |
| `operatorLabel`, `reason` | Safe bounded attribution/reason under the shared field table. |
| `expectedAccessRevision` | Integer `0` for pristine first-administrator bootstrap. Other repair uses its target's authoritative reviewed revision. |
| `expectedIdentityId` | Kratos identity UUID of the candidate shown during verified login. |
| `identityProof` | Exactly `{kind: hydra-access-token, accessToken: <secret>}` as a typed secret-bearing JSON object. No alternative proof/fallback. |
| `responsibility` | Bootstrap omits it. Repair requires one exact typed variant below. |

Each responsibility has a required `kind` discriminator. `kind: group-manager` contains only `projectId`, `accessGroupId` in addition to `kind`. `kind: action-grantor` contains only the typed exact `target` and `actionId` in addition to `kind`. The verified recipient comes from the proof, not a replacement principal assertion. A repair cannot request arbitrary assignments or unrelated actions.

The selected first-setup design keeps a freshly obtained Hydra access token transient. Its unadmitted-human producer remains unavailable. Host/container execution supplies maintenance authority. The backend privately introspects the token using its configured Hydra, checking access-token kind, active/expiry, trusted issuer/client/API audience/scope. It loads current Kratos identity eligibility and matches the stable subject to `expectedIdentityId`. This reuses the [accepted CLI identity verification](human-cli-login.md#human-cli-authentication) and [private introspection](https://www.ory.com/docs/hydra/guides/oauth2-token-introspection). It proves a current Hydra access grant and current Kratos identity, not that the CLI holds a live Kratos browser cookie.

Only first-administrator bootstrap may proceed without existing local admission. It requires an authoritative unclaimed, pristine installation and a verified identity without a conflicting local link, then commits the new identity link, admission, fixed four Organization assignments, audit and original outcome together. An existing suspended/recovery-blocked identity is not made eligible through bootstrap. Repair requires the proof's already active admitted human and target Project membership where applicable. Under current locks/revision, prove the exact responsibility has no remaining active eligible human before saving just its repair. Group repair explicitly saves membership and management together. Ordinary product endpoints retain their normal admission/action checks.

Generate one immutable installation UUID during managed initialization, before admission. Persist it in authoritative backend installation metadata and bind the operator-controlled managed-installation record to it through the verified host channel. Reuse it across restarts, upgrades and target-label changes. A missing/mismatched binding fails maintenance. Do not regenerate or accept an API-reported identity as host proof. Restoring an installation preserves its identity and follows existing restore reconciliation, while a deliberate new installation/factory reset obtains a new identity. This is a logical initialization contract, not a new implemented table or migration.

Retain a keyed fingerprint of normalized mode/installation/verified subject/target/action/revision/request meaning, excluding the replaceable token bytes. Each attempt still verifies its currently valid proof. This allows a refreshed credential for the same recipient to recover the original host operation. A changed subject, intent or original reviewed revision conflicts. Do not store the proof in audit, response cache or original request. A completed replay finds the original before applying fresh-write stranded/unclaimed checks and cannot restore subsequently removed grants.

`MaintenanceResponse` is one stdout JSON object with `schemaVersion: 1`, `operationId`, `installationId`, `principalId`, `accessRevision`, and `outcome: bootstrapped` or `repaired`, plus the exact safe repaired `responsibility` only for repair. Replays return the original outcome. They do not claim current rights. Controlled failures return one safe `MaintenanceErrorResponse` with `schemaVersion: 1`, `operationId` when parsed, and `code`, without input values or secrets. Exit 0 is successful/replayed outcome. Exit 2 is malformed/unsupported input. Exit 1 is a controlled failed operation. Error codes are `invalid_input`, `invalid_identity_proof`, `identity_ineligible`, `installation_mismatch`, `stale_revision`, `idempotency_key_reused`, `idempotency_in_progress`, `already_bootstrapped`, `responsibility_not_stranded`, `dependency_unavailable`, `unexpected_error`. Unexpected failures return the safe `unexpected_error` object when the response boundary can still emit it, with private diagnostics under the existing reporting rules. An absent/interrupted response is an unknown outcome: retry the same host operation with valid same-identity proof, not a new claim or a product-token bypass.

<a id="human-proof-acquisition-prerequisite"></a>

## Human proof acquisition prerequisite

The transient Hydra recipient proof must come from the accepted [human CLI login transaction](human-cli-credential-lifecycle.md#cli-login-transaction), including [PD-ACCESS-07](decision-human-cli-issuer-binding.md)'s exact issuer-bound callback defense. Validate both success and error association before exchange, retain complete attempt context in memory and hand the access token directly into protected host stdin. Do not substitute an ID/refresh token, scraped cookie, administrative test approval or ad hoc token-minting procedure. Host execution and the independently verified installation binding still authorize the operation. Current private Hydra/Kratos and coordinated local eligibility/generation checks still identify and constrain its recipient.

The maintained acquisition capability and rendered operator journey remain unavailable and unqualified. Complete human sign-in, fresh proof, protected repair and rename acceptance is deferred to [human operator qualification (#298)](https://github.com/matejpalenik/inframeld/issues/298), with acquisition prerequisites still owned by [#82](https://github.com/matejpalenik/inframeld/issues/82) and [#160](https://github.com/matejpalenik/inframeld/issues/160). Server-side proof verification or a staged provider test does not establish a usable acquisition procedure. Bootstrap and broader repair retain their stated delivery limits. Recording the callback decision or deferring human acceptance does not close the operator acquisition gap or waive current proof, authorization, protected-input, replay, backend, SDK or CI requirements.

<a id="machine-readable-input-shape"></a>

## Machine-readable input shape

[The design-only JSON Schema](../../../../contracts/design/access/maintenance-v1.schema.json) expresses the documented envelope. It is not a runtime model or proof of authorization, trusted event ordering or provider completion. PD-ACCESS-03 is resolved by ADR-0085. Recovery continuation is implemented by [RecoveryMaintenanceMapper](../../../../apps/backend/src/inframeld_backend/access/cli/mappers/recovery_maintenance_mapper.py) and the owning application capability above. The narrow [Project metadata repair consumer](#project-metadata-authority-repair) is implemented by [ProjectMetadataMaintenanceMapper](../../../../apps/backend/src/inframeld_backend/access/cli/mappers/project_metadata_maintenance_mapper.py) and its owning application capability. The private first-administrator bootstrap consumer is implemented. Group repair and other action-repair variants remain design-only and unsupported. PD-ACCESS-04 is resolved under ADR-0082. Any maintenance path that first provisions a human must follow [the accepted identity-coordination workflow](identity-admission-coordination.md), whose shared coordinator and recovery/initialization participants are implemented. First provisioning through maintenance remains unfinished.

A structural validator cannot establish received-byte limits, reject duplicate JSON keys after decoding, verify a credential or enforce database state. JSON Schema treats `1` and `1.0` as the same integer value. The implemented consumers enforce strict token parsing separately. Future broader bootstrap/repair implementation must reconcile or supersede this design schema with its runtime-owned definition.

<a id="authorization-failure-scenarios"></a>

## Authorization failure scenarios

| Situation | Required outcome |
| --- | --- |
| A host repair uses a stale installation/responsibility revision. | Reject without partial assignments. A host token or target label alone is insufficient proof. |
| A maintenance request or private callback exceeds its body bound or includes extra fields. | Reject before admitting effects, without reflecting protected input in the error. |
| Maintenance proof expires after the original bootstrap response is lost. | A currently verified replacement token for the same subject may recover the original host operation. The token itself is not retained or fingerprinted as stable meaning. |
