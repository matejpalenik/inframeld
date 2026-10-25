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

The accepted boundary is a narrow one-shot maintenance command executed inside the verified managed backend using the operator's existing host/container-exec authority. Supply bounded protected input, an expected immutable installation identity, independently verified Ory identity and the exact reviewed request state. An ordinary bearer token, email address, target label or Docker context name is not operator authority or sufficient installation proof. Remote host maintenance remains separate from ordinary remote CLI login. Do not expose a public claim/maintenance API, shared claim password or backend Docker socket.

First-administrator setup commits the verified identity link, admission, four explicit organization grants and audit together. Replaying the same original claim returns that result without recreating removed grants. A competing identity fails. For repair, the replacement must already be an active admitted verified human. Recheck under the applicable organization/project locks that the exact responsibility is still stranded and the reviewed revision is current. A stale review fails without partial assignments. Save the operator reason, before/after revisions and audit with the exact membership/management or use-and-grant repair. The audit explains the action but cannot prevent misuse by a trusted host operator. The [maintenance contract](#maintenance) selects `inframeld-maintenance`, one protected versioned JSON request limited to 64 KiB, independent verification of the candidate's current Ory session/identity, exact reviewed intent and safe output. Host execution authorizes repair. The session proof identifies its recipient. The [version 1 maintenance draft](#maintenance-wire) uses the transient Hydra human access token already obtained by the CLI as protected recipient identity proof. Private introspection and current Kratos identity checks precede local reads. Host execution supplies authority. First bootstrap may verify before local admission, while repair requires an active admitted eligible recipient. The draft specifies installation-identity initialization and versioned input/output/error/replay contracts for final review and qualification.

Deliver suspension/restoration and scoped operator maintenance as explicit capabilities, separate from ordinary membership/grant administration. The immediate local block, external Kratos/Hydra cleanup and deliberate restoration have separate recorded outcomes: cleanup failure cannot lift the block. A retry inspects or continues the original cleanup. It never restores access merely to make another provider request. Operator maintenance uses a privileged host boundary, not an unrestricted token or hidden bypass in ordinary CLI authentication. The [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) assigns these workflows and their specification/security qualification prerequisites. No maintenance command is implemented by this guide.

<a id="maintenance"></a>

<a id="one-shot-maintenance-through-protected-stdin"></a>

## One-shot maintenance through protected stdin

The accepted backend-only command name is `inframeld-maintenance`, with separate first-administrator bootstrap and exact stranded-authority repair intents. Read one JSON request from protected stdin, limited to **64 KiB (65,536 bytes)**. This is a command contract, not an implemented executable or runnable example.

| Required input | Meaning |
| --- | --- |
| `schemaVersion` | Explicit input-contract version. |
| `expectedInstallationId` | Installation identity from operator-controlled installation state, compared with authoritative persistent backend identity. |
| Original `operationId` | Identify the original claim/repair for safe replay. |
| Operator attribution and reason | Safe accountable description of the host action. |
| Exact responsibility/target and reviewed revision | Bootstrap's fixed Organization assignments, or the one reviewed stranded relationship/action being repaired. |
| Candidate identity and current Ory session proof | Independently verify the candidate's current session and trusted Ory identity, not a caller-supplied email or subject assertion. |

Host/container execution authorizes maintenance. The candidate's proof identifies the human who receives the exact assignments. Bootstrap may admit a verified human not yet locally admitted. Repair requires an already active admitted human. Consume proof secrets only through protected input and verification. Never put them in argv, environment, logs, audit or replay records. Safe output contains exact outcome, IDs and revisions. The [version 1 maintenance draft](#maintenance-wire) specifies input/output models, mode literals, transient Hydra access-token proof and installation-identity initialization for final review. Runtime qualification remains required.

Existing host/container-exec authority admits maintenance. Verify installation identity against authoritative managed state and identity evidence through the trusted Ory boundary. Do not trust a caller's target label, email, Docker context or product bearer. Recheck stranded state and revisions under the normal organization/project coordination. Save only the reviewed replacement assignments and audit together. No network maintenance API, shared claim password or backend Docker socket is introduced.

<a id="maintenance-wire"></a>

<a id="version-1-host-maintenance-input-and-proof"></a>

## Version 1 host-maintenance input and proof

Run the backend-only `inframeld-maintenance` command once with a versioned JSON object through protected stdin, maximum 64 KiB. Select `schemaVersion: 1` and `mode: bootstrap-first-administrator` or `repair-stranded-authority`. Reject unknown fields, duplicate object keys and a second JSON value. No secret argument, environment variable, browser-cookie extraction, refresh token or ID token is supported.

| Field | Required value |
| --- | --- |
| `schemaVersion`, `mode` | Version 1 and one of the two modes above. |
| `expectedInstallationId` | UUID from the independently operator-controlled installation record. |
| `operationId` | Original nonblank opaque host operation ID, maximum 128 characters. |
| `operatorLabel`, `reason` | Safe bounded attribution/reason under the shared field table. |
| `expectedAccessRevision` | Reviewed Organization revision for bootstrap/Organization action, otherwise the target's authoritative Project revision. |
| `expectedIdentityId` | Kratos identity UUID of the candidate shown during verified login. |
| `identityProof` | Exactly `{kind: hydra-access-token, accessToken: <secret>}` as a typed secret-bearing JSON object. No alternative proof/fallback. |
| `responsibility` | Bootstrap omits it. Repair requires one exact typed variant below. |

Each responsibility has a required `kind` discriminator. `kind: group-manager` contains only `projectId`, `accessGroupId` in addition to `kind`. `kind: action-grantor` contains only the typed exact `target` and `actionId` in addition to `kind`. The verified recipient comes from the proof, not a replacement principal assertion. A repair cannot request arbitrary assignments or unrelated actions.

The CLI keeps its freshly obtained Hydra access token transient during first setup. Host/container execution supplies maintenance authority. The backend privately introspects the token using its configured Hydra, checking access-token kind, active/expiry, trusted issuer/client/API audience/scope. It loads current Kratos identity eligibility and matches the stable subject to `expectedIdentityId`. This reuses the [accepted CLI identity verification](human-cli-login.md#human-cli-authentication) and [private introspection](https://www.ory.com/docs/hydra/guides/oauth2-token-introspection). It proves a current Hydra access grant and current Kratos identity, not that the CLI holds a live Kratos browser cookie.

Only first-administrator bootstrap may proceed without existing local admission. It requires the unclaimed installation and the legitimate unique identity link, and commits admission, fixed four Organization assignments, audit and original outcome together. An existing suspended/recovery-blocked identity is not made eligible through bootstrap. Repair requires the proof's already active admitted human and target Project membership where applicable. Under current locks/revision, prove the exact responsibility has no remaining active eligible human before saving just its repair. Group repair explicitly saves membership and management together. Ordinary product endpoints retain their normal admission/action checks.

Generate one immutable installation UUID during managed initialization, before admission. Persist it in authoritative backend installation metadata and bind the operator-controlled managed-installation record to it through the verified host channel. Reuse it across restarts, upgrades and target-label changes. A missing/mismatched binding fails maintenance. Do not regenerate or accept an API-reported identity as host proof. Restoring an installation preserves its identity and follows existing restore reconciliation, while a deliberate new installation/factory reset obtains a new identity. This is a logical initialization contract, not a new implemented table or migration.

Retain a keyed fingerprint of normalized mode/installation/verified subject/target/action/revision/request meaning, excluding the replaceable token bytes. Each attempt still verifies its currently valid proof. This allows a refreshed credential for the same recipient to recover the original host operation. A changed subject, intent or original reviewed revision conflicts. Do not store the proof in audit, response cache or original request. A completed replay finds the original before applying fresh-write stranded/unclaimed checks and cannot restore subsequently removed grants.

`MaintenanceResponse` is one stdout JSON object with `schemaVersion: 1`, `operationId`, `installationId`, `principalId`, `accessRevision`, and `outcome: bootstrapped` or `repaired`, plus the exact safe repaired `responsibility` only for repair. Replays return the original outcome. They do not claim current rights. Controlled failures return one safe `MaintenanceErrorResponse` with `schemaVersion: 1`, `operationId` when parsed, and `code`, without input values or secrets. Exit 0 is successful/replayed outcome. Exit 2 is malformed/unsupported input. Exit 1 is a controlled failed operation. Error codes are `invalid_input`, `invalid_identity_proof`, `identity_ineligible`, `installation_mismatch`, `stale_revision`, `idempotency_key_reused`, `idempotency_in_progress`, `already_bootstrapped`, `responsibility_not_stranded`, `dependency_unavailable`, `unexpected_error`. Unexpected failures return the safe `unexpected_error` object when the response boundary can still emit it, with private diagnostics under the existing reporting rules. An absent/interrupted response is an unknown outcome: retry the same host operation with valid same-identity proof, not a new claim or a product-token bypass.

<a id="machine-readable-input-shape"></a>

## Machine-readable input shape

[The design-only JSON Schema](../../../../contracts/design/access/maintenance-v1.schema.json) expresses the documented envelope. It is not a runtime model or proof of authorization, trusted event ordering or provider completion. PD-ACCESS-03 and PD-ACCESS-04 retain their existing pending scope.

A structural validator cannot establish received-byte limits, reject duplicate JSON keys after decoding, verify a credential or enforce database state. JSON Schema treats `1` and `1.0` as the same integer value. Strict token parsing remains a separate requirement. Future implementation must reconcile or supersede this design schema with its runtime-owned definition.

<a id="authorization-failure-scenarios"></a>

## Authorization failure scenarios

| Situation | Required outcome |
| --- | --- |
| A host repair uses a stale installation/responsibility revision. | Reject without partial assignments. A host token or target label alone is insufficient proof. |
| A maintenance request or private callback exceeds its body bound or includes extra fields. | Reject before admitting effects, without reflecting protected input in the error. |
| Maintenance proof expires after the original bootstrap response is lost. | A currently verified replacement token for the same subject may recover the original host operation. The token itself is not retained or fingerprinted as stable meaning. |
