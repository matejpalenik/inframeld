# Access contracts for CLI-first v1

**Status:** accepted specification decisions for #116, reviewed with the developer on 2026-10-04, with the authorized concrete HTTP/maintenance/recovery draft below ready for final review. These contracts do not establish implemented routes, physical tables, generated schemas or runtime qualification. [Access control](access-control.md) owns the explanation of authorization and recovery. This reference owns the fixed identifiers, initial assignments and contract handoff. Domain guides own the workflows behind each action.

For example, Alice creates Support's Pipeline and explicitly grants SupportBot permission to edit it. SupportBot can save a supported configuration, build under its separate Build grant and run authorized evaluations. It cannot create a second Pipeline, delegate its permissions or change a protected audience. Producing a new configuration revision is part of editing the existing Pipeline.

## Contents

| Question | Contract |
| --- | --- |
| Which action, target and caller combinations exist? | [Fixed catalogue](#capability-catalogue) |
| What may applications create or update? | [Provisioning boundary](#provisioning) |
| What does a human receive after creation? | [Initial assignments](#initial-assignments) |
| Who controls imported test-case audiences? | [Evaluation audience administration](evaluation.md#case-audiences) |
| How are new humans invited? | [Invitations](#invitations) |
| What must application operations carry? | [Operation contracts](#operation-contracts) |
| How are existing HTTP symbols preserved? | [Transport mapping](#transport-mapping) |
| What do session checks return and how long may they wait? | [Sessions and authentication budgets](#session-checks) |
| Which mutation and grant bounds apply? | [Mutation profile](#mutation-profile), [grant administration](#grant-management) |
| What can key issuance and replay reveal? | [Application-key lifecycle](#key-lifecycle) |
| What may private recovery callbacks carry? | [Recovery callback boundary](#recovery-callbacks) |
| What is the host maintenance input? | [Maintenance boundary](#maintenance) |
| What are the exact new routes, symbols and fields? | [Concrete HTTP draft](#http-operation-matrix) |
| How does the CLI prove the maintenance recipient? | [Version 1 maintenance input/proof](#maintenance-wire) |
| What is the private recovery integration handoff? | [Version 1 callback contract](#recovery-wire) |
| What remains before #116 closes? | [Review and remaining work](#review-and-remaining-work) |

<a id="capability-catalogue"></a>

## Fixed action catalogue

Identifiers use descriptive kebab-case. Preserve the published `create-access-groups` and the already accepted `query` and `feedback:write` literals. Each row is one action on the exact indicated target. A grant on one Pipeline, Deployment, Collection, Source, connection or profile supplies no rights on another. Unsupported action/target or action/principal-kind combinations are denied, including during grant assignment. There are no custom roles or future-action wildcards.

Applications may receive **can use** only for eligible actions. Humans may receive **can use** or **can use and grant**. This is the same authorization model, with deliberate eligibility restrictions. Current principal/project eligibility, membership, credential restrictions and protected-input checks remain necessary. The catalogue does not replace them. Basic visibility and the fixed Edit-includes-View rule follow [Access visibility](access-control.md#section-hide-inaccessible-resources).

| Identifier | Exact target | Eligible caller | Meaning and owning checks |
| --- | --- | --- | --- |
| `admit-users` | Organization | Human | Admit verified humans or issue admission invitations; identity proof and current authority remain separate from login. |
| `suspend-users` | Organization | Human | Immediately block a human even if responsibilities become stranded. |
| `restore-users` | Organization | Human | Deliberately restore a suspended human after identity/security review and required cleanup. |
| `create-projects` | Organization | Human | Create an additional ordinary project; starter provisioning remains separate. |
| `manage-project-members` | Project | Human | Add/remove eligible members and review membership invitations; not grant administration. |
| `create-access-groups` | Project | Human | Create a project-local group and explicitly initialize human membership/management. |
| `create-application-accounts` | Project | Human | Create an empty application account and its creator administration assignments; no key or inherited rights. |
| `create-pipelines` | Project | Human | Create a Pipeline and its fixed creator assignments. |
| `create-deployments` | Project | Human | Create a Deployment with a ready compatible initial version and fixed creator assignments. |
| `manage-upload-defaults` | Project | Human | Change future upload audiences, managing every old/new group. |
| `delete-project` | Project | Human | Block and erase project-owned contents under the project-deletion contract; does not grant reading. |
| `inspect-budget` | Project | Human or application | Inspect permitted budget information; accounting schemas belong to the model contract. |
| `manage-budget` | Project | Human | Set, raise, lower or remove its limit through the guarded policy operation. |
| `manage-trace-policy` | Project | Human | Change recording/retention within operator policy; imports use the same checks. |
| `delete-trace-history` | Project | Human | Explicitly erase selected trace history; ordinary expiry/source erasure remains backend work. |
| `inspect-feedback` | Project | Human or application | Inspect protected reports; cannot edit another caller's rating. |
| `create-collections` | Project | Human | Create an empty Collection definition; does not admit Documents. |
| `create-sources` | Project | Human | Create a reviewed source definition with explicit destination groups; credentials/sync remain separate. |
| `create-model-connections` | Project | Human | Create non-secret connection configuration; provider credentials and optional testing remain separate. |
| `create-processing-profiles` | Project | Human | Create a named immutable processing definition; does not process data. |
| `create-embedding-profiles` | Project | Human | Create a named immutable vector definition; does not generate vectors. |
| `query` | Pipeline or Deployment, separately | Human or application | Execute saved working configuration or released serving selection respectively; neither target includes the other. |
| `inspect-query-traces` | Pipeline or Deployment, separately | Human or application | Inspect query evidence under current access to every captured source, including uncited candidates. |
| `build-pipeline` | Pipeline | Human or application | Prepare a ready version; policy-controlled publication additionally needs the selected Deployment's release authority. |
| `view-pipeline-configuration` | Pipeline | Human or application | Read permitted non-secret saved configuration/history without revealing linked inaccessible resources. |
| `edit-pipeline-configuration` | Pipeline | Human or application | Save/restore supported configuration revisions; does not manage shared connections or publish. |
| `delete-pipeline` | Pipeline | Human or application | Request its narrower guarded lifecycle deletion; not document erasure or project deletion. |
| `view-deployment-configuration` | Deployment | Human or application | Read permitted non-secret configuration. |
| `edit-deployment-configuration` | Deployment | Human or application | Edit non-serving details; changing serving selection requires Manage releases. |
| `manage-releases` | Deployment | Human or application | Publish, manage candidates/canaries, rollback, switch mode and select automatic inputs under readiness/revision checks. |
| `delete-deployment` | Deployment | Human or application | Request guarded Deployment deletion; does not erase underlying Documents. |
| `feedback:write` | Deployment | Human or application | Read/write own live-answer rating with current Query, original principal and protected receipt checks. |
| `generate-evaluation-cases` | Pipeline | Human or application | Separately admit model work and save unreviewed candidates. |
| `view-evaluation-cases` | Pipeline | Human or application | Read/history/export under current case audiences and linked sources. |
| `edit-evaluation-cases` | Pipeline | Human or application | Edit/import/link verified evidence/remove future selection; changed content is unreviewed. |
| `review-evaluation-cases` | Pipeline | Human or application | Accept/reject exact revisions, recording the actual principal and kind. |
| `run-evaluation` | Pipeline | Human or application | Execute with Pipeline Query and current case/source/model/budget checks. |
| `inspect-evaluation-results` | Pipeline | Human or application | Inspect protected runs/comparisons; not general diagnostic trace browsing. |
| `manage-evaluation-case-audiences` | Pipeline | Human | Change saved import audience or explicitly selected cases' audiences, managing every old/new group. |
| `view-collection` | Collection | Human or application | Inspect permitted definition/membership metadata; reading contents still requires document access. |
| `edit-collection` | Collection | Human or application | Change logical corpus membership through ordinary revisions; not erase Documents or widen audiences. |
| `delete-collection` | Collection | Human or application | Delete the collection definition subject to live dependencies; does not erase admitted Documents. |
| `view-source-configuration` | Source | Human or application | Inspect permitted non-secret source configuration. |
| `edit-source-configuration` | Source | Human | Change its guarded configuration/destination binding; does not change existing document audiences. |
| `sync-source` | Source | Human or application | Start bounded sync through ordinary admission, saved group Add/Update rights and collection mutation checks. |
| `manage-source-credentials` | Source | Human | Bind/replace/remove source credentials through protected input; cannot retrieve stored plaintext. |
| `delete-source` | Source | Human | Stop future sync and retire configuration/credentials; does not erase already admitted Documents. |
| `view-model-connection-configuration` | Model connection | Human or application | Read permitted non-secret connection configuration. |
| `use-model-connection` | Model connection | Human or application | Use supported roles/models through ModelGateway under current access, credential and spending checks. |
| `manage-model-connection` | Model connection | Human | Guarded shared configuration/credential administration, preserving live-impact and embedding-compatibility checks. |
| `delete-model-connection` | Model connection | Human | Guarded retirement; no silent provider fallback or dependency rebinding. |
| `view-processing-profile` | Processing profile | Human or application | Inspect its immutable permitted definition. |
| `use-processing-profile` | Processing profile | Human or application | Select it for ordinary authorized processing/preparation. |
| `view-embedding-profile` | Embedding profile | Human or application | Inspect its immutable permitted definition. |
| `use-embedding-profile` | Embedding profile | Human or application | Select it for ordinary authorized compatible vector preparation/querying. |
| `add-documents` | Access group | Human or application | Add on every selected audience group; does not grant document reading. |
| `update-documents` | Access group | Human or application | Update on every authoritative current audience group; preserve the audience. |
| `delete-documents` | Access group | Human or application | Delete on every current audience group; erase all Document versions under normal cleanup. |
| `issue-application-keys` | Application account | Human | Exact-account authority plus ability to grant every current account action/manage every account group. |
| `revoke-application-keys` | Application account | Human | Independent revocation authority, including the last key; no issuance delegation requirement. |
| `delete-application-account` | Application account | Human | Retire the account and revoke keys while preserving project-owned work. |

Group membership/management, document sharing and grant administration are guarded relationships/operations, not extra wildcard actions. Grant-management reads and writes require current can-use-and-grant for that exact action/target. For document Add/Update/Delete assignments on an Access group, its current eligible manager may also administer those assignments through the existing group-management relationship; this supplies neither document-operation use nor membership to another group. Own-access inspection is principal-bound. There is no general product audit-browser permission or API. Non-query diagnostic trace browsing is [deferred in v1](observability.md#non-query-diagnostics).

<a id="provisioning"></a>

## Human provisioning and application updates

V1 creation of Projects, access groups, application accounts, Pipelines, Deployments, Collections, Sources, model connections and processing/embedding profiles is human-only. Applications start with no rights and receive only explicit eligible use grants. Application-driven provisioning and the associated human grant-initialization binding are deferred, rather than implemented as an unused interface.

Supported updates to existing resources remain available to applications under their exact grants. A permitted operation may produce Documents, DocumentVersions, CollectionRevisions, configuration revisions, PipelineVersions, jobs, receipts or Evaluation cases/revisions. This is workflow output, not a bypass for creating configurable resources. Human-only source/model administration, audience management, credentials, grants and budget/tracing changes remain human-only even through import.

An application configuration-import plan may reuse compatible existing resources and apply eligible supported updates. A missing resource or changed immutable profile requiring creation makes that plan ineligible. Reject a known-ineligible plan before its mutations. Report the dependency that an authorized human must provision, then allow a new reviewed plan. Never switch to a saved human, invent a replacement profile or silently omit requested work. Later authority/state changes retain the normal partial-outcome and original-operation recovery rules.

<a id="initial-assignments"></a>

## Explicit initial human assignments

Creation checks current human eligibility and the matching Project Create action, then saves the resource, the following exact-resource **can-use-and-grant** assignments, audit and original-request outcome together. No partial resource/grant state remains on transactional failure. Initial assignments are removable grants, not creator authority. A retry recovers the original result without recreating removed grants. New defaults do not automatically backfill existing resources or projects.

| New resource | Fixed creator assignments |
| --- | --- |
| Additional Project | Seventeen: `manage-project-members`, `create-access-groups`, `create-application-accounts`, `create-pipelines`, `create-deployments`, `manage-upload-defaults`, `delete-project`, `inspect-budget`, `manage-budget`, `manage-trace-policy`, `delete-trace-history`, `inspect-feedback`, `create-collections`, `create-sources`, `create-model-connections`, `create-processing-profiles`, `create-embedding-profiles`. Requires Organization `create-projects`; starter provisioning has its separate admission boundary. |
| Pipeline | Thirteen: `query`, `inspect-query-traces`, `build-pipeline`, `view-pipeline-configuration`, `edit-pipeline-configuration`, `delete-pipeline`, the six Evaluation operational actions above, and `manage-evaluation-case-audiences`. |
| Deployment | Seven: `query`, `inspect-query-traces`, `manage-releases`, `view-deployment-configuration`, `edit-deployment-configuration`, `delete-deployment`, `feedback:write`. A ready compatible initial version is required. |
| Collection | `view-collection`, `edit-collection`, `delete-collection`. |
| Source | `view-source-configuration`, `edit-source-configuration`, `sync-source`, `manage-source-credentials`, `delete-source`. |
| Model connection | `view-model-connection-configuration`, `use-model-connection`, `manage-model-connection`, `delete-model-connection`. |
| Processing profile | `view-processing-profile`, `use-processing-profile`. |
| Embedding profile | `view-embedding-profile`, `use-embedding-profile`. |
| Application account | `issue-application-keys`, `revoke-application-keys`, `delete-application-account`, assigned to the human creator. The application receives no initial actions, groups or key. |

Access-group creation explicitly initializes the eligible human as both ordinary member and manager, without granting unrelated document actions. First-administrator bootstrap retains the four Organization assignments `admit-users`, `suspend-users`, `restore-users` and `create-projects`. Private starter provisioning retains its explicit project/resource/group assignments through the owning workflow and does not grant `create-projects`.

Profiles remain immutable. There is no profile Edit or force-deletion capability in this decision. Normal reference/retention cleanup does not mutate their meaning. These fixed assignments do not supply document membership, provider secrets, model use on other resources or automatic publication authority.

<a id="invitations"></a>

## Single-use invitations with current authority

An invitation is an opaque, revocable, single-use admission/assignment intent. Its default lifetime is seven days and its maximum thirty days, both operator-configurable, with the default no greater than the maximum. A human may request a shorter lifetime. The invitation secret is protected input, not a grant, identity proof, URL to log, or audit payload. Generate the invitation token from 32 cryptographically random bytes. Store only a digest for verification and safe metadata, never a replayable plaintext invitation. Issuance delivers the secret once under the [secret-operation recovery rules](jobs-and-idempotency.md#secrets).

Issuance records the issuer, exact intended admission/membership/group/action assignments, installation/project/target bindings, expiry and original operation. Check current issuer authority for every intended effect. Retain the existing v1 invitation admission boundary: every invitation needs current `admit-users`, plus `manage-project-members` for requested membership, current group management for group assignment, and can-use-and-grant for every requested exact action/target or the existing current group-manager delegation alternative for document-action assignments on that group. Ordinary direct membership/grant changes for already admitted humans remain their separate operations; this decision does not add a broader membership-only invitation capability. An invitation does not combine these into an unrestricted Invite role.

Activation is a narrow admission operation. It accepts a currently verified Kratos browser identity through its cookie, cookie-write CSRF protection and the protected invitation token, before ordinary local admission is required. Do not reuse an ordinary human-session dependency that already requires an admitted principal. This admission exception admits only invitation activation, not ordinary product operations. The concrete draft also supplies a narrowly scoped, non-consuming preview for the accepted requirement to show intended scope; preview admits no principal and saves no assignments. Neither operation can restore a suspended human, release a recovery block or replace their required security review.

Activation requires verified Ory authority/subject identity, an unused/unexpired/unrevoked invitation and current issuer eligibility and authority for every promised assignment. Bind the verified subject to the stable local principal; never merge people or infer authority by matching email. Show the intended scope to the recipient without leaking unrelated inventory. Reject stale/ineligible intent rather than silently activating a broader or smaller assignment set.

Consume the invitation with its guarded local effects and audit under the appropriate coordination. Concurrent uses cannot assign twice; a lost response recovers the original recorded activation rather than granting again. Revocation does not remove assignments from a completed activation. External Ory onboarding and local activation retain distinct outcomes. Issuance takes an explicit typed assignment set, optional shorter lifetime and expected access revision. Revocation addresses the exact invitation and reviewed revision. Activation records the original operation against the verified recipient and exact invitation. A current invitation or issuer change cannot cause partial activation. The [concrete HTTP draft](#http-operation-matrix) maps route/operation/request/response symbols for final review. Provider integration remains a qualification prerequisite.

<a id="operation-contracts"></a>

## Application operation inputs, results and failures

The following are semantic application contracts, not new published DTO/class names or final JSON field spellings. Inputs use application-owned typed IDs and verified caller context. Each operation checks current authority itself. A review by a client does not authorize a later save.

| Operation family and owner | Required input | Result and failure behavior |
| --- | --- | --- |
| Resource creation — owning domain with Access initialization | Verified human caller, exact parent Project/Organization, typed definition and original operation identity | Resource ID plus committed initial assignments/outcome. Deny application callers; reject unavailable names/invalid dependencies; original replay cannot recreate grants. |
| Configuration/membership update — resource owner | Verified caller, exact resource ID, supported change, reviewed expected revision and original operation | New committed revision or original outcome. Stale state conflicts; wrong action/kind denies; immutable meaning is never overwritten. |
| Grant administration — Access | Verified human, recipient ID/kind, fixed action/exact target, level and expected access revision | Exact committed assignment/removal and revision. Deny unsupported combinations, missing delegation or stranded ordinary handover; reads reveal only assignments the caller may administer. |
| Case/import audience change — Evaluation with Access | Verified human, Pipeline ID, explicit case selections or future-import setting, authoritative old/proposed group IDs and expected revisions | Saved audience/revision, audit and bounded outcome. Deny missing Pipeline action or any old/new group management; stale selection conflicts. [Evaluation](evaluation.md#case-audiences) owns the full contract. |
| Case import — Evaluation | Verified caller, Pipeline ID, protected content/identity/provenance, reviewed destination audience/revision and verified optional source mappings | Protected cases/revisions, reused/changed/unresolved outcomes; changed content is unreviewed. An application uses the saved human-approved audience and cannot override it. |
| Invitation issue/revoke/activate — Access with Ory boundary | Exact intended assignments, verified issuer/recipient identity as appropriate, bounded secret/lifetime, expected state and original operation | Safe invitation/activation outcome; issuance delivers its secret once. Expired/revoked/used/stale/ineligible intent cannot assign; recover original activation after response loss. |
| Identity recovery cleanup — Access with identity adapters | Authenticated server-side, flow-bound evidence; stable subject/principal; original operation; independent provider outcome evidence | Temporary product block and durable Kratos/Hydra obligations. Uncertain cleanup stays blocked; duplicates cannot revoke later sessions or release newer obligations. |
| Project deletion/status — Access and owning cleanup workflows | Verified human, exact Project, original operation and reviewed state | Immediate block and durable shutdown/erasure; narrow content-free original-operation status can survive membership removal. No private content in status. |
| Host bootstrap/stranded repair — Access maintenance boundary | Protected versioned host input, verified installation and Ory identity, exact expected responsibility/revision, operator/reason and original operation | Narrow assignment plus audit/revision or conflict. No ordinary product bearer authority or global administrative bypass. |

Identity/credential failures, permission denial, hidden-resource 404, stale state and retry conflicts retain the [existing problem contract](error-handling.md#authentication-contract). Do not relabel provider unavailability as invalid credentials or lost permission as empty data. Secret-bearing operations retain [show-once recovery](jobs-and-idempotency.md#secrets). Paid work uses ordinary admission and uncertain-dispatch rules, not blind retries.

<a id="transport-mapping"></a>

## Preserve transport names and declare credential families

Keep existing published routes, operation IDs and schema names. The inspected `GET /v1/session` uses `getCurrentSession` and returns `principalId`; its implemented adapter accepts Kratos human cookies. The accepted extension adds Hydra human bearer to that human operation. The separately accepted `GET /v1/application-session`, `getCurrentApplicationSession`, returning `principalId` and `projectId`, remains design until implemented. [API session contracts](api-contracts.md#session-contracts) own these mappings.

Every protected HTTP operation must declare supported credential families before implementation. Ordinary product operations authenticate supported Kratos cookies, Hydra human bearer or HTTP application-key bearer, then check principal-kind eligibility and the exact action. A verified application at an ordinary human-only provisioning or administration operation receives 403. Identity-specific session checks restrict the credential family instead: an application key at the human-session check, or a human credential at the application-session check, receives 401. Invitation activation has the narrow provider-verified cookie admission boundary above. These family declarations must not turn human-only operations into application permissions. Both bearer families use Authorization; full verification and no fallback remain mandatory. Cookie-authenticated writes require CSRF. MCP retains only its existing two-tool application-key profile and does not gain provisioning or human OAuth tools.

Unsupported route credential families use the established 401 outcome; a supported, verified but ineligible principal/action receives 403. Competing/malformed credentials are rejected before provider I/O. Public documentation/health remain public and credential-free. Qualification must align native OpenAPI declarations, generated clients and runtime enforcement.

<a id="session-checks"></a>

## Session responses and authentication budgets

Both accepted session checks return HTTP 200 with `Cache-Control: no-store` and the normal server-generated `X-Request-ID`. Resource IDs are UUID strings. Preserve the existing human response containing only `principalId`. The application response contains only `principalId` and its bound `projectId`. Neither operation returns permissions or a status snapshot, probes a model or writes local access. A later operation checks current authority again.

| Configurable limit | Starting default | Meaning |
| --- | --- | --- |
| One provider-verification call | 5 seconds | Bound each required Kratos/Hydra call by the remaining total budget. |
| Complete backend authentication check | 10 seconds | Cover required provider verification and current local eligibility checks. Do not add individual timeouts into an unbounded request. |
| CLI session-check request | 15 seconds | Allow the backend check and transport overhead before reporting an unconfirmed connection check. |

These are accepted starting limits, not measured latency guarantees. The inspected [Kratos cookie adapter](../../apps/backend/src/inframeld_backend/access/infrastructure/verifiers/kratos_browser_session_verifier.py) already defaults to five seconds per call. The overall deadline and CLI limit still need implementation and qualification. Wait for providers outside database sessions, use short independent local reads after verification, and admit no success after the authentication deadline. Do not use cross-request positive authentication caches, verifier fallback or blind server verification retries. Timeout behavior must not disclose whether a protected identity exists. [Authentication errors](error-handling.md#authentication-contract) preserve 503 for required verification that cannot be confirmed.

<a id="mutation-profile"></a>

## Bounded Access mutation profile

New Access-management JSON bodies are limited to **32 KiB (32,768 bytes)**. New bulk assignment requests carry at most **100 explicit assignments**. Reject unknown fields in new request schemas. These limits do not apply to document uploads or complete domain configuration payloads. Preserve existing published schema names, field behavior and restrictions rather than silently tightening them through a shared replacement model.

Use camelCase wire fields, UUID strings for known resource identities, an opaque string `operationId`, UTC timestamps and strictly nonnegative integer revisions. Access writes carry `expectedAccessRevision`; other owners retain their domain-specific revision inputs. Every mutation carries exactly one `Idempotency-Key`, at most 128 characters. The original operation is found before treating today's revision as a new write, with current authentication/authorization still required to recover it. [Jobs and idempotency](jobs-and-idempotency.md#requests) own request identity and recovery.

A local change saves its domain effects, revision, audit and original outcome together. Use 201 for creation, 200 for completed metadata changes and 202 when durable cleanup remains. Return the original operation identity, appropriate resource identity, committed revision and safe outcome through the owning operation's typed result. A 202 response means accepted work, not completed erasure. This profile does not introduce a generic operation envelope or command framework. The [concrete HTTP draft](#http-operation-matrix) supplies the new request/response symbols and oversize-response declarations for final review.

<a id="grant-management"></a>

## Exact grant management and bounded reads

Preserve the implemented `POST /v1/projects/{project_id}/grants`, `assignProjectUseOnlyGrant`, `ProjectUseOnlyGrantRequest` and `ProjectUseOnlyGrantResponse`. Its supported action remains `create-access-groups` and its result remains `canGrant: false`. Full administration uses separately named operations rather than changing that published use-only contract.

Full assignment, downgrade and removal identify the exact target, recipient and fixed action, and carry the expected access revision. Assignment/downgrade explicitly state `canGrant` as a boolean. An application recipient may receive only an eligible use-only assignment. Every management operation requires an eligible human with current can-use-and-grant for that exact action/target, or the existing group-manager authority for document-action assignments on that group, and retains scope, last-administrator and current-state checks. Reject unsupported action/target/recipient combinations rather than storing an unusable grant.

List assignments for one exact target and required `actionId`, with current can-use-and-grant for that action or the existing current group-manager authority for document-action assignments on that group. Use the [existing bounded pagination contract](pagination.md): default 25, maximum 100, stable recipient-ID order and current authority on every page. Do not broaden this into a project-wide administrator inventory. Mutation results describe the original committed change and access revision. Use a fresh authorized read to learn the current assignment. The [full-administration draft](#http-operation-matrix) specifies routes, operation IDs and request/result models for final review.

<a id="key-lifecycle"></a>

## Application-key issuance, revocation and secret recovery

Issuance is a human-only operation on the exact application account. Its input contains the optional lifetime, explicit supported HTTP/MCP adapter restrictions and expected access revision. The server derives the installation and project bindings and checks the account's current rights. A caller cannot submit an alternative permission set through key issuance. Preserve [full issuance authority](access-control.md#applications), the configurable 90-day default/365-day maximum and the limit of two usable keys across audiences.

The first successful issuance returns safe key metadata, the newly generated key and `secretAvailable: true`. A replay returns the same key identity and safe metadata with `secretAvailable: false`, without plaintext or another key. Plaintext is never a cached idempotency result. Revocation blocks use immediately under its separate human exact-account authority. Metadata inspection never retrieves the secret. Account retirement revokes keys while preserving project-owned work and uses a durable accepted outcome only while cleanup remains. The [HTTP draft](#http-operation-matrix) supplies their exact new route/schema symbols for review, preserving the accepted credential format.

<a id="maintenance"></a>

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

Host/container execution authorizes maintenance; the candidate's proof identifies the human who receives the exact assignments. Bootstrap may admit a verified human not yet locally admitted. Repair requires an already active admitted human. Consume proof secrets only through protected input and verification. Never put them in argv, environment, logs, audit or replay records. Safe output contains exact outcome, IDs and revisions. The [version 1 maintenance draft](#maintenance-wire) specifies input/output models, mode literals, transient Hydra access-token proof and installation-identity initialization for final review. Runtime qualification remains required.

Existing host/container-exec authority admits maintenance. Verify installation identity against authoritative managed state and identity evidence through the trusted Ory boundary; do not trust a caller's target label, email, Docker context or product bearer. Recheck stranded state and revisions under the normal organization/project coordination. Save only the reviewed replacement assignments and audit together. No network maintenance API, shared claim password or backend Docker socket is introduced.

<a id="recovery-callbacks"></a>

## Private recovery admission and completion

Private admission/completion callbacks use a dedicated rotatable hook secret. It is neither an application key nor a human credential, and these callbacks are not ordinary product client operations. Allowlist only `schemaVersion`, `flowId`, `identityId`, `eventKind` and `phase` in callback JSON, with a maximum of **8 KiB (8,192 bytes)**. The server validates the configured provider/installation binding. Do not accept caller-selected principals, assignments, sessions to revoke or provider success flags as authority. Callback bodies and audit contain no cookies/tokens.

Derive stable event identity from the installation, flow, event kind and phase, rather than a randomly generated delivery ID. Save the original cleanup obligation and product block before pending cleanup could permit old credentials to regain access. Native Kratos cleanup follows, then trusted ordered completion evidence, independent durable Hydra cleanup and eligible release of this operation's block. A repeated admission recovers its original obligation. A completed duplicate cannot start broad cleanup of later logins. Failed/uncertain outcomes keep the block, and an older operation cannot release a newer one.

The hook secret authenticates the sending service. It does not, by itself, certify a verified reset or completed native cleanup. Those meanings must follow qualified placement and provider evidence. The [version 1 recovery draft](#recovery-wire) supplies private route/header/version/enum declarations and trusted evidence requirements for final review. Qualify ordering, delivery/reconciliation behavior and legitimate-session preservation on pinned OSS releases under #117. Product OpenAPI/generated clients do not gain a recovery bypass.

Recovery/reset separately uses authenticated server-side admission and trusted completion evidence with native Kratos cleanup and durable independent Hydra cleanup. The temporary block must be committed before old credentials could regain product access. Preserve the legitimate recovery session using qualified provider evidence, not a guessed generic webhook session ID. [Recovery](access-control.md#identity-recovery-cleanup) owns the invariant; #117 must qualify ordering, failures, evidence, deduplication and session preservation on pinned OSS releases before this integration is relied upon.

<a id="http-operation-matrix"></a>

## Concrete HTTP contract draft

**Review status:** the product boundaries and route patterns above are accepted. The exact new operation/model names and field bounds below are the concrete engineering draft for final maintainer review. A read-only specification review on 2026-10-04 found no remaining blocking inconsistencies after the scope, query encoding, invitation preview and delegation corrections. They are not generated OpenAPI, implemented Python symbols or permission changes. Preserve existing published symbols. Native OpenAPI will be generated from owning backend code when implementation is authorized.

For example, Alice sets SupportBot's `query` assignment on Support's Pipeline with `canGrant: false` and the reviewed access revision. If the response is lost, her same idempotency key recovers that original assignment result under current authority. Removing that assignment returns a removal result, not `canGrant: false`: the latter still permits use. If SupportBot is subsequently given another grant, replay of Alice's old removal cannot remove it again.

### Credential and response profiles

Each matrix row selects one of these profiles. This is documentation notation, not a runtime framework or a new credential type.

| Profile | Credential families and local eligibility |
| --- | --- |
| Human session | Kratos cookie or Hydra human access-token bearer. Requires admitted, currently eligible human. Unsupported application family is 401. |
| Application session | HTTP application-key bearer only, with current account/project checks. Unsupported human family is 401. |
| Human administration | Authenticate supported Kratos cookie, Hydra human bearer or HTTP application-key bearer, then require an admitted eligible human and the row's exact authority. A verified application is 403. Cookie writes require CSRF. |
| Invitation activation | Verified Kratos browser cookie plus cookie-write CSRF before local admission. Other credential families are 401. Existing suspension/recovery blocks remain effective. |
| Invitation preview | The same verified Kratos cookie and CSRF boundary before local admission, solely for protected-token scope inspection. Other credential families are 401; existing suspension/recovery blocks remain effective. No consumption or product authority follows. |
| Own human access | Same supported families as ordinary product operations, but only an eligible human may inspect their own assignments. A verified application is 403. No caller-selected principal. |
| Private recovery | Dedicated service secret only on the private listener. No product credential family or product client operation. |

All HTTP responses use the existing request correlation and problem representation. Sensitive identity/access metadata and secret-bearing responses use `Cache-Control: no-store`. New JSON inputs reject unknown fields and duplicate object keys. Decode bounded UTF-8 JSON, require its declared object shape, and reject duplicate scalar query parameters. GET inputs have no body. Every product mutation requires the existing single bounded `Idempotency-Key`; invitation activation's identity binding is specified below. Private recovery uses event deduplication instead of that product header.

Declare 400 for competing/malformed authentication, 401 for failed or unsupported credentials, 403 for verified ineligibility/action denial, 404 for missing/hidden resources, 409 for stale revision or idempotency/state conflict, 422 for invalid fields/cursors, and 503 for unconfirmed required dependencies where applicable. New bounded HTTP bodies additionally declare **413**. Preserve the existing generic mapper for 413 and unsupported-media-type 415: `type: about:blank`, `code: http_error`, the standard HTTP status phrase as title, and detail `The request could not be completed.` Do not reflect input or introduce custom exception details. Body bounds are measured on received bytes before decoding/admitting effects. Provider/credential messages never become public problem details.

An unchanged successful PUT or already-completed revocation/removal records a safe original no-change outcome, with the current revision and no re-created assignment. A real access change increments the coordinated access revision once. A replay returns the original status/result, not a freshly executed mutation. Existing published commands retain their own response behavior. All new results below include `operationId`, `accessRevision` and `idempotencyExpiresAt`, except read/session/private-event results and the owner-specific deletion outcome explicitly identified below.

### Exact failure and recovery decisions

| Condition after the applicable visibility/authority checks | Outcome |
| --- | --- |
| Required credential is missing/invalid or wrong family for an identity-specific operation | 401 `http_error`; applicable trusted challenge, no fallback. |
| Competing/malformed authentication header input | 400 `invalid_authentication_request` before provider I/O. |
| Verified caller is blocked, lacks exact authority, or an application requests human administration | 403 `access_denied`; no hidden-account detail. |
| Target/recipient is missing or hidden under ordinary scope/visibility | 404 `resource_not_found`. A known UUID is not visibility. |
| Unsupported closed action/target/recipient-kind combination or invalid new-model field | 422 `invalid_input` or existing bounded `validation_error` for parsing; no stored unusable grant. |
| Reviewed access revision no longer matches | 409 `stale_revision` on fresh work. Original exact replay is resolved before this check. |
| Same idempotency key, different meaningful request | 409 `idempotency_key_reused`; no second mutation. |
| Same original operation currently reserved/in progress | Existing 409 `idempotency_in_progress` or retained original result after completion; no duplicate attempt. |
| Ordinary removal/demotion would strand authority; group remains referenced; key count already two usable; completed invitation used for a new activation | 409 `conflict`; no partial local effects. |
| Verified recipient/current dependency becomes ineligible before commit | 409 `conflict` under safe disclosure; a caller's own ineligibility remains 403. |
| Required provider state or persistence cannot be confirmed | 503 `dependency_unavailable`; fail closed, keep any already committed cleanup block. |
| Bounded HTTP request body is too large or media type unsupported | Safe 413/415 `http_error`; no echo, reservation or mutation. |

Invalid/expired/revoked invitation tokens on new activation use the same safe 404 outcome rather than revealing token state or intended resources. The verified recipient is still required. Stale/ineligible issuer assignment intent returns safe 409, with no partial consumption. Secret-bearing response loss returns only the original safe issuance metadata; no plaintext cache or second credential follows. Private recovery's flow/evidence conflicts and host errors have the exact separate contracts below.

### Sessions and preserved command

| Method and route | Operation ID | Input / response | Profile and success |
| --- | --- | --- | --- |
| `GET /v1/session` | Existing `getCurrentSession` | No input / existing `CurrentSessionResponse`, only `principalId` | Human session; 200. Cookie implementation exists, bearer extension remains planned. |
| `GET /v1/application-session` | `getCurrentApplicationSession` | No input / `CurrentApplicationSessionResponse`: `principalId`, `projectId` | Application session; 200. |
| `POST /v1/projects/{project_id}/grants` | Existing `assignProjectUseOnlyGrant` | Existing `ProjectUseOnlyGrantRequest` / `ProjectUseOnlyGrantResponse` | Human administration; existing 201 and published `create-access-groups` / `canGrant: false` restrictions unchanged. |

### Full action-grant operations

For each concrete base below, register three distinct operations: `PUT {base}/grants/{recipient_principal_id}/{action_id}`, `DELETE` at that same route, and `GET {base}/grants`. The table enumerates the symbols, rather than introducing a generic resource registry or catch-all grant endpoint. `action_id` is a catalogue literal appropriate to that target. Colon-containing accepted literals such as `feedback:write` retain their value after normal URL decoding.

| Exact base | PUT / DELETE / GET operation IDs | Result target field and model stem |
| --- | --- | --- |
| `/v1/organizations/{organization_id}` | `setOrganizationActionGrant` / `removeOrganizationActionGrant` / `listOrganizationActionGrants` | `organizationId`; `OrganizationActionGrant` |
| `/v1/projects/{project_id}` | `setProjectActionGrant` / `removeProjectActionGrant` / `listProjectActionGrants` | `projectId`; `ProjectActionGrant` |
| `/v1/projects/{project_id}/access-groups/{access_group_id}` | `setAccessGroupActionGrant` / `removeAccessGroupActionGrant` / `listAccessGroupActionGrants` | `projectId`, `accessGroupId`; `AccessGroupActionGrant` |
| `/v1/projects/{project_id}/application-accounts/{application_principal_id}` | `setApplicationAccountActionGrant` / `removeApplicationAccountActionGrant` / `listApplicationAccountActionGrants` | `projectId`, `applicationPrincipalId`; `ApplicationAccountActionGrant` |
| `/v1/pipelines/{pipeline_id}` | `setPipelineActionGrant` / `removePipelineActionGrant` / `listPipelineActionGrants` | `pipelineId`; `PipelineActionGrant` |
| `/v1/deployments/{deployment_id}` | `setDeploymentActionGrant` / `removeDeploymentActionGrant` / `listDeploymentActionGrants` | `deploymentId`; `DeploymentActionGrant` |
| `/v1/collections/{collection_id}` | `setCollectionActionGrant` / `removeCollectionActionGrant` / `listCollectionActionGrants` | `collectionId`; `CollectionActionGrant` |
| `/v1/sources/{source_id}` | `setSourceActionGrant` / `removeSourceActionGrant` / `listSourceActionGrants` | `sourceId`; `SourceActionGrant` |
| `/v1/model-connections/{model_connection_id}` | `setModelConnectionActionGrant` / `removeModelConnectionActionGrant` / `listModelConnectionActionGrants` | `modelConnectionId`; `ModelConnectionActionGrant` |
| `/v1/processing-profiles/{processing_profile_id}` | `setProcessingProfileActionGrant` / `removeProcessingProfileActionGrant` / `listProcessingProfileActionGrants` | `processingProfileId`; `ProcessingProfileActionGrant` |
| `/v1/embedding-profiles/{embedding_profile_id}` | `setEmbeddingProfileActionGrant` / `removeEmbeddingProfileActionGrant` / `listEmbeddingProfileActionGrants` | `embeddingProfileId`; `EmbeddingProfileActionGrant` |

Each PUT request is the named `{Stem}Request` containing only required `canGrant` and `expectedAccessRevision`. Its `{Stem}Response` adds the table's target fields, `recipientPrincipalId`, `actionId`, `canGrant` and `changed` to the mutation result fields. Return 201 for a new assignment and 200 for changing or confirming the existing assignment. Do not turn PUT into removal.

DELETE has no body and requires query `expectedAccessRevision`. Its `{Stem}RemovalResponse` contains the mutation result fields, target fields, `recipientPrincipalId`, `actionId`, `removed: true` and `changed`. `removed` describes the original post-change absence, not a stored grant level or current authorization. Return 200, including an authorized already-absent no-change result. An old replay never removes a later assignment.

GET requires one `actionId` plus ordinary `limit`/`cursor`. Return 200 `PageResponse[{Stem}ItemResponse]`; each item has the target fields, `recipientPrincipalId`, `actionId` and `canGrant`. The exact target and action are bound into the cursor, ordered by recipient UUID. Current eligible human can-use-and-grant on that action/target is required for all three operations, alongside current scope/membership and last-administrator rules. For group Add/Update/Delete assignments, the existing current group-manager relationship is also sufficient to administer those assignments, as the [document-operation guide](access-control.md#documents) states. Management never substitutes for an Add/Update/Delete use grant. Applications may be recipients only for eligible use-only actions.

`GET /v1/projects/{project_id}/grant-recipients`, operation `listProjectGrantRecipients`, requires scalar query fields `targetKind`, `targetId` and `actionId`, plus ordinary `limit`/`cursor`. `targetKind` is one of the closed target literals below except `organization`; `targetId` is the corresponding resource/principal UUID. The HTTP boundary converts that pair into the appropriate typed target. For `project`, `targetId` must equal the path Project; for every other kind, load its authoritative parent and require that same Project. Require current caller Project membership/visibility and current can-use-and-grant for the exact target/action, or its existing group-manager document-action authority. Return `PageResponse[GrantRecipientResponse]` with only `principalId`, `displayName`, `kind`, ordered by principal UUID, disclosing only eligible current members of that Project. Bind Project, exact target and action into the cursor. Do not accept JSON/deep-object query targets, a request body, Organization targets or cross-Project targets. This is not an installation directory. Organization recipients are supplied by verified admitted principal ID; no global directory is added.

### Admission, memberships and lifecycle

In the following table, `revision` means the required `expectedAccessRevision` field, and `names` means required `name` and `displayName`. All rows use Human administration unless stated otherwise. The single installation's Organization ID is explicit, not an implicit superadministrator scope. A body revision always refers to the coordinated Organization or Project access revision, not a credential or resource content revision.

| Method and route | Operation ID | Request / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/organizations/{organization_id}/human-admissions` | `admitHuman` | `HumanAdmissionRequest`: `identityId`, `expectedAccessRevision`; `HumanAdmissionResponse`: mutation fields, `organizationId`, `principalId`, `changed` | `admit-users`; verify current configured Kratos identity and unique authority/subject link; 201 new admission, 200 already-admitted no change. Never restore a blocked principal. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/suspend` | `suspendHuman` | `HumanSuspensionRequest`: revision, `reason`; `HumanSuspensionResponse`: mutation fields, organization/principal IDs, `accessBlocked: true`, `cleanupOperationId` | `suspend-users`; 202 after immediate suspension/block plus original durable cleanup obligation commit. No handover prerequisite. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/restore` | `restoreHuman` | `HumanRestorationRequest`: revision, `securityReviewReference`; `HumanRestorationResponse`: mutation fields, organization/principal IDs | `restore-users`; 200 only after current stable Kratos identity, same legitimate principal, required confirmed cleanup, security review and no pending newer block. Does not recreate relationships. |
| `POST /v1/projects` | `createProject` | `ProjectCreationRequest`: `organizationId`, `name`, `displayName`, revision; `ProjectCreationResponse`: mutation fields, `projectId`, names and fixed seventeen `initialGrants` | Organization `create-projects`; 201; save creator membership/grants/audit/result together. Starter provisioning remains #27's separate workflow. |
| `PUT /v1/projects/{project_id}/members/{principal_id}` | `addProjectMember` | `ProjectMembershipRequest`: revision; `ProjectMembershipResponse`: mutation fields, project/principal IDs, `member: true`, `changed` | `manage-project-members`; admitted eligible human recipient only; 201 added or 200 unchanged. Application membership comes from account creation. |
| `DELETE /v1/projects/{project_id}/members/{principal_id}` | `removeProjectMember` | Revision query / `ProjectMembershipRemovalResponse`: mutation fields, IDs, `removed: true`, `changed` | `manage-project-members`; 200; ordinary handover, remove that human's project grants/groups/managers together. Application retirement is separate. |
| `POST /v1/projects/{project_id}/access-groups` | `createAccessGroup` | `AccessGroupCreationRequest`: names, revision; `AccessGroupCreationResponse`: mutation fields, `projectId`, `accessGroupId`, names, `creatorPrincipalId` | `create-access-groups`; 201 with creator membership/management together, no extra document grants. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}` | `addAccessGroupMember` / `removeAccessGroupMember` | `AccessGroupMembershipRequest`: revision (PUT) or revision query (DELETE); `AccessGroupMembershipResponse` / `AccessGroupMembershipRemovalResponse`: mutation fields, project/group/principal IDs, `member: true` or `removed: true`, `changed` | Current group manager; admitted current project human/application recipient; PUT 201/200, DELETE 200. Removal removes management too under handover. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}` | `appointAccessGroupManager` / `removeAccessGroupManager` | `AccessGroupManagerRequest`: revision (PUT) or revision query (DELETE); `AccessGroupManagerResponse` / `AccessGroupManagerRemovalResponse`: mutation fields, IDs, `manager: true` or `removed: true`, `changed` | Current group manager; eligible human recipient only; appointment explicitly saves membership; PUT 201/200, DELETE 200. Demotion retains membership; preserve last eligible manager. |
| `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}` | `deleteAccessGroup` | Revision query / `AccessGroupDeletionResponse`: mutation fields, IDs, `removed: true` | Current group manager; 200 only if unused under all stored document/source/upload/default/case references; otherwise 409. |
| `POST /v1/projects/{project_id}/application-accounts` | `createApplicationAccount` | `ApplicationAccountCreationRequest`: names, revision; `ApplicationAccountCreationResponse`: mutation fields, `projectId`, `principalId`, names, fixed three human `initialGrants` | `create-application-accounts`; 201; application starts with no actions, groups or key. Account identity is its shared principal ID, not a second account UUID. |
| `DELETE /v1/projects/{project_id}/application-accounts/{application_principal_id}` | `deleteApplicationAccount` | Revision query / `ApplicationAccountDeletionResponse`: mutation fields, project/application principal IDs, `accessBlocked: true`, optional `cleanupOperationId` | Exact `delete-application-account`; 200 if local retirement/key revocation complete, 202 if durable cleanup remains. Preserve project-owned work. |
| `DELETE /v1/projects/{project_id}` | `deleteProject` | Revision query / owning #204/#124 deletion outcome | Exact `delete-project` plus current human/project membership; 202 on new admission. See semantic handoff below rather than selecting a new job schema. |
| `GET /v1/projects/{project_id}/my-access` | `getMyProjectAccess` | No body / `MyProjectAccessResponse`: `projectId`, `principalId`, `accessRevision`, bounded `grants`, `groupMemberships`, `groupManagements`, `nextCursor` | Own human access; current project member, actual caller only; 200; no other principal's assignments or hidden linked resources. |
| `GET /v1/my-organization-access` | `getMyOrganizationAccess` | No body / `MyOrganizationAccessResponse`: `organizationId`, `principalId`, `accessRevision`, Organization `grants` | Own human access; 200 for actual admitted human only; no installation inventory. |

`securityReviewReference` is a safe audit reference supplied by the authorized human who performed the legitimate-identity/security review. It is not proof by itself, a new automated review service or a way to change the identity link. The service checks current configured Kratos identity against the stable link and all required original cleanup obligations. Restoration remains the deliberate responsibility described in [Access](access-control.md#identity-recovery-cleanup).

`GET /v1/projects/{project_id}/members` (`listProjectMembers`) requires `manage-project-members`. The group's `/members` (`listAccessGroupMembers`) and `/managers` (`listAccessGroupManagers`) require current group management. Return the existing bounded page of safe `principalId`, `displayName`, `kind`, ordered by principal UUID, with the exact scope bound into the cursor. They do not expose other memberships or document contents. Own Project access uses one combined page of at most `limit` entries across its three arrays, ordered by relationship kind then target UUID then action literal, and a scope/principal-bound cursor. A grant item contains typed `target`, `actionId`, `canGrant`; membership/management items contain only `accessGroupId`. Return only stored assignments and actual relationships, not fabricated implied grant rows. `nextCursor` is a string or null. Organization own-access lists only its four supported stored action assignments. A page reports a current access revision for that read; it is not a permission snapshot for later execution.

### Invitations and key routes

| Method and route | Operation ID | Named input / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/invitations` | `issueInvitation` | `InvitationIssueRequest` / `InvitationIssueResponse` | Human administration; current `admit-users` and all promised assignment authorities; 201. |
| `POST /v1/invitations/{invitation_id}/revoke` | `revokeInvitation` | `InvitationRevocationRequest`: `expectedAccessRevision` / `InvitationRevocationResponse` | Human administration; original issuer currently eligible with `admit-users`, or current can-use-and-grant on `admit-users` for the Organization; 200. No authority over completed assignments follows. |
| `POST /v1/invitations/preview` | `previewInvitation` | `InvitationPreviewRequest` / `InvitationPreviewResponse` | Invitation preview profile; 200 for current safe intended scope; no consumption, reservation or admission. |
| `POST /v1/invitations/activate` | `activateInvitation` | `InvitationActivationRequest` / `InvitationActivationResponse` | Invitation activation profile; 200 after guarded consumption/admission/assignments. |
| `POST /v1/projects/{project_id}/application-accounts/{application_principal_id}/keys` | `issueApplicationKey` | `ApplicationKeyIssueRequest` / `ApplicationKeyIssueResponse` | Exact `issue-application-keys` plus every current delegation/group check; 201. |
| `GET` at the same keys route | `listApplicationKeys` | Pagination query / `PageResponse[ApplicationKeyMetadataResponse]` | Exact Issue or Revoke keys; 200; key UUID order, safe metadata only. |
| `GET` at that route plus `/{key_id}` | `getApplicationKey` | No body / `ApplicationKeyMetadataResponse` | Exact Issue or Revoke keys; 200; no secret retrieval. |
| `POST` at that route plus `/{key_id}/revoke` | `revokeApplicationKey` | `ApplicationKeyRevocationRequest` / `ApplicationKeyRevocationResponse` | Exact `revoke-application-keys`; 200; immediate revocation independent of issuance delegation. |

The key rows use Human administration. `ApplicationKeyIssueRequest` has only `allowedAdapters`, optional `expiresInSeconds` and required `expectedAccessRevision`; `ApplicationKeyRevocationRequest` has only required `expectedAccessRevision`. Bind each key to the account/project in the path, not just its public key UUID. Safe key metadata contains `keyId`, `applicationPrincipalId`, `projectId`, `prefix` (only `ifm_app_`, never secret bytes), `allowedAdapters`, `createdAt`, `expiresAt`, and nullable `revokedAt`. Metadata is not a copy of account permissions. Issuance derives installation/API-audience/project binding from authoritative configuration. `allowedAdapters` is a required nonempty unique subset of `http`, `mcp`. Optional `expiresInSeconds` is a strict positive integer within the configured maximum; omission uses the configured default. Revocation takes only the required expected revision.

`ApplicationKeyIssueResponse` contains mutation fields, `metadata`, `secretAvailable` and optional `key`. `key` is present only with `secretAvailable: true` on first delivery. Safe replay has `secretAvailable: false` and omits `key`. `ApplicationKeyRevocationResponse` contains mutation fields and safe `metadata`; it never carries a secret or verifier. The retained issuance result describes the original created credential; fresh metadata inspection establishes its current revocation/expiry state.

`InvitationIssueRequest` contains `organizationId`, required `assignments`, `expectedAccessRevision`, `expectedProjectAccessRevisions` and optional `expiresInSeconds`. Each assignment has a required `kind` discriminator selecting one closed typed variant: `project-membership` with `projectId`; `group-membership` or `group-manager` with `projectId`/`accessGroupId`; or `action-grant` with a typed exact `target`, `actionId` and `canGrant`. A `group-manager` intent explicitly includes ordinary group membership; it does not implicitly create Project membership. Assignments apply to the activating human, never a caller-selected application. Admission itself is the invitation's baseline effect. Require 1–100 unique assignments; use an explicit `kind: admission-only` variant with no additional fields, as the sole item, for an invitation with no project assignments. Reject incompatible mixtures, duplicate identities or multiple levels for the same intended grant.

Project-scoped effects require either the activating human's current eligible Project membership or an explicit `project-membership` intent for that Project in this invitation. Group/action intents never silently add that relationship. Issuance validates targets and all requested authority but cannot promise an unknown recipient's existing relationships. Activation checks the actual verified recipient and fails atomically with safe 409 if a prerequisite is absent. This permits an explicit grant-only intent for an already-admitted member without inserting another effect or widening issuer authority. Group assignments still require the current group-manager authority; group document-action grant intents retain the documented group-manager delegation alternative. All targets must bind to this Organization/installation and their authoritative affected Project.

The typed `target` variants have `kind` and exactly their corresponding UUID fields: `organization` (`organizationId`), `project` (`projectId`), `access-group` (`projectId`, `accessGroupId`), `application-account` (`projectId`, `applicationPrincipalId`), `pipeline` (`pipelineId`), `deployment` (`deploymentId`), `collection` (`collectionId`), `source` (`sourceId`), `model-connection` (`modelConnectionId`), `processing-profile` (`processingProfileId`), `embedding-profile` (`embeddingProfileId`). The server loads authoritative parent scope/kind and validates current catalogue combinations. These are closed transport shapes, not an unchecked persistence discriminator or a generic grant-management API. Invitation issuance additionally requires `expectedProjectAccessRevisions`, an array of unique `{projectId, accessRevision}` records matching every affected Project exactly, maximum 100, empty for admission-only/Organization-only intent. For a multi-Project invitation, check those reviewed revisions and current authority under the normal Organization then sorted Project locks. Activation revalidates the saved intended assignments against current authority/state in all affected scopes; it does not treat issuance revisions as a permanent permission snapshot.

`InvitationIssueResponse` contains mutation fields, `invitationId`, `organizationId`, safe intended `assignments`, `expiresAt`, `secretAvailable` and first-delivery-only `invitationToken`. Token generation is 32 random bytes, encoded as 43 unpadded base64url characters, with SHA-256 digest-only verification and constant-time comparison. Tokens are not URLs or identity proofs. Safe replay omits the token. Revocation request has `expectedAccessRevision`; its response has mutation fields, invitation/Organization IDs and `revoked: true`.

`InvitationPreviewRequest` contains only `invitationToken`, in the protected JSON body rather than a URL/query/log. Although POST is used to protect this input, preview is a read and requires no `Idempotency-Key`. Verify the current Kratos identity, existing local blocks if linked, the unused/unexpired/unrevoked token, current issuer eligibility/authority and target state. Return safe 404 for invalid/expired/revoked/used tokens and safe 409 for stale/ineligible intent; no partial effect follows. `InvitationPreviewResponse` contains `invitationId`, `organizationId`, safe intended `assignments`, `expiresAt` and `scopes`, a bounded array of `InvitationScopeResponse` items containing only typed `target` and authoritative `displayName`. Include the baseline Organization, affected Projects and explicitly intended targets, deduplicated, at most 201 items for the 100-assignment bound. No document content, provider details, issuer inventory or secret is returned. The account UI (#82) shows these names, exact assignment levels and expiry before asking the recipient to activate. Preview never consumes the token or promises later success: activation rechecks current state.

`InvitationActivationRequest` has only `invitationToken`; its 200 response has `operationId`, `invitationId`, `organizationId`, `principalId`, committed `organizationAccessRevision`, bounded `projectAccessRevisions` and `idempotencyExpiresAt`. Before local admission exists, bind the reservation to the independently verified configured Kratos authority/subject, exact invitation and route/key. After commit retain the resulting stable principal binding. Lookup the original activation before treating consumed state as a new activation. Replay requires the same currently verified recipient, eligible local state and current access to the safe outcome; it cannot grant again, switch recipient, restore removed assignments or bypass an expired/revoked credential. Expiry/unused/current issuer authority apply to new consumption; they do not turn a completed original replay into another invitation. A different key cannot consume an already used invitation. Safe activation exposes only the recipient's intended scope, not a list of issuer-controlled resources.

### Shared wire field bounds and owner-specific handoffs

| Field | Draft wire constraint |
| --- | --- |
| Resource/principal/identity IDs | UUID strings converted into their distinct application-owned runtime ID types. Preserve accepted UUID versions/zero values. Only generated key IDs are explicitly UUIDv4. |
| `operationId`, `cleanupOperationId` | Opaque nonblank string, maximum 128 characters. Correlation, not authority. |
| Revisions | JSON bodies require strict integer numbers, 0–9,223,372,036,854,775,807 inclusive; JSON booleans/strings/floats are invalid. Query revisions use one decimal scalar matching `0` or `[1-9][0-9]{0,18}`, parsed within the same range; reject signs, whitespace, leading zeros, decimal points, exponent notation and duplicate parameters. |
| Boolean fields | Strict JSON boolean. Acknowledgments required by an operation are literal `true`. |
| `name` | Draft new-model bound 1–64 characters with the accepted ASCII selector grammar. Reserved-word and migration behavior stay with #151's naming contract; no silent normalization. |
| `displayName` | Draft new-model bound 1–128 Unicode characters, nonblank. Never an identity selector. |
| `reason` | Nonblank safe free text, maximum 512 characters. Never request credentials or private content here. |
| `securityReviewReference`, `operatorLabel` | Nonblank safe text, maximum 128 characters. An audit reference/attribution, not verified authority. |
| Credential input values | Secret-safe values, bounded by the relevant body/token format; never echoed in validation errors. |
| Times | UTC RFC 3339 timestamps. Lifetime arithmetic and overflow are validated before effects. |
| Pagination | Existing `limit` 1–100, default 25 and `cursor` bound 1024; feature validates exact scope/action/filter/order. |

All initial-grant result items contain the typed exact `target`, `actionId` and literal `canGrant: true`, without document memberships or fabricated actions. Newly created Project results return its access revision; their input expected revision protects Organization creation authority. Newly created group/account results return their owning Project access revision. Read and validate each authoritative parent binding before accessing resource-specific grant rows.

Domain-owned Pipeline/configuration/query/Evaluation/model/budget/tracing/feedback payloads retain their existing specification owners. #116 supplies their fixed exact action/target/principal eligibility and protected transport/replay rules, not replacement domain APIs. Source-derived inspection additionally checks every current protection; an Access grant never overrides those checks.

Project-deletion admission is the #204 application operation consumed by #124/#38/#45: input is verified human caller, exact `ProjectId`, `expectedAccessRevision` and original operation identity. Commit block, audit, original result and cleanup obligation together. The semantic result distinguishes admitted/access-blocked, application/key shutdown unfinished, physical cleanup unfinished and complete, as the [existing deletion contract](jobs-and-idempotency.md#project-deletion) requires. Worker cleanup remains bound to that admitted scope even after ordinary membership changes. A retained content-free projection checks the currently eligible original initiating principal and operation binding after membership removal, returns no private inventory/counts/content, and grants no cancellation/continuation. Those owners select its route/schema/retention without a second job enum in #116.

<a id="maintenance-wire"></a>

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
| `responsibility` | Bootstrap omits it; repair requires one exact typed variant below. |

Each responsibility has a required `kind` discriminator. `kind: group-manager` contains only `projectId`, `accessGroupId` in addition to `kind`. `kind: action-grantor` contains only the typed exact `target` and `actionId` in addition to `kind`. The verified recipient comes from the proof, not a replacement principal assertion. A repair cannot request arbitrary assignments or unrelated actions.

The CLI keeps its freshly obtained Hydra access token transient during first setup. Host/container execution supplies maintenance authority. The backend privately introspects the token using its configured Hydra, checking access-token kind, active/expiry, trusted issuer/client/API audience/scope. It loads current Kratos identity eligibility and matches the stable subject to `expectedIdentityId`. This reuses the [accepted CLI identity verification](access-control.md#human-cli-authentication) and [private introspection](https://www.ory.com/docs/hydra/guides/oauth2-token-introspection). It proves a current Hydra access grant and current Kratos identity, not that the CLI holds a live Kratos browser cookie.

Only first-administrator bootstrap may proceed without existing local admission. It requires the unclaimed installation and the legitimate unique identity link, and commits admission, fixed four Organization assignments, audit and original outcome together. An existing suspended/recovery-blocked identity is not made eligible through bootstrap. Repair requires the proof's already active admitted human and target Project membership where applicable. Under current locks/revision, prove the exact responsibility has no remaining active eligible human before saving just its repair. Group repair explicitly saves membership and management together. Ordinary product endpoints retain their normal admission/action checks.

Generate one immutable installation UUID during managed initialization, before admission. Persist it in authoritative backend installation metadata and bind the operator-controlled managed-installation record to it through the verified host channel. Reuse it across restarts, upgrades and target-label changes. A missing/mismatched binding fails maintenance; do not regenerate or accept an API-reported identity as host proof. Restoring an installation preserves its identity and follows existing restore reconciliation, while a deliberate new installation/factory reset obtains a new identity. This is a logical initialization contract, not a new implemented table or migration.

Retain a keyed fingerprint of normalized mode/installation/verified subject/target/action/revision/request meaning, excluding the replaceable token bytes. Each attempt still verifies its currently valid proof. This allows a refreshed credential for the same recipient to recover the original host operation; a changed subject, intent or original reviewed revision conflicts. Do not store the proof in audit, response cache or original request. A completed replay finds the original before applying fresh-write stranded/unclaimed checks and cannot restore subsequently removed grants.

`MaintenanceResponse` is one stdout JSON object with `schemaVersion: 1`, `operationId`, `installationId`, `principalId`, `accessRevision`, and `outcome: bootstrapped` or `repaired`, plus the exact safe repaired `responsibility` only for repair. Replays return the original outcome; they do not claim current rights. Controlled failures return one safe `MaintenanceErrorResponse` with `schemaVersion: 1`, `operationId` when parsed, and `code`, without input values or secrets. Exit 0 is successful/replayed outcome; exit 2 is malformed/unsupported input; exit 1 is a controlled failed operation. Error codes are `invalid_input`, `invalid_identity_proof`, `identity_ineligible`, `installation_mismatch`, `stale_revision`, `idempotency_key_reused`, `idempotency_in_progress`, `already_bootstrapped`, `responsibility_not_stranded`, `dependency_unavailable`, `unexpected_error`. Unexpected failures return the safe `unexpected_error` object when the response boundary can still emit it, with private diagnostics under the existing reporting rules. An absent/interrupted response is an unknown outcome: retry the same host operation with valid same-identity proof, not a new claim or a product-token bypass.

<a id="recovery-wire"></a>

## Version 1 private recovery handoff

Expose only on the private service listener, excluded from public ingress/product OpenAPI/generated clients:

| Route | Private operation ID | Input / acknowledgment |
| --- | --- | --- |
| `POST /internal/v1/identity-recovery/admit` | `admitIdentityRecovery` | `IdentityRecoveryEventRequest`, `phase: admit` / 202 `IdentityRecoveryEventResponse` |
| `POST /internal/v1/identity-recovery/complete` | `completeIdentityRecovery` | Same named input, `phase: complete` / 202 same acknowledgment |

Require exactly one `X-Inframeld-Recovery-Key`, verified in constant time against configured dedicated hook-secret material. Product cookie/Authorization credentials cannot substitute. Keep the service secret in protected configuration; rotate with bounded current/next overlap, then retire the old secret. These adapters do not invoke product human/application authentication or cookie CSRF.

The request's exact five fields are `schemaVersion: 1`, UUID `flowId`, UUID `identityId`, `eventKind: recovery` or `password-reset`, and `phase: admit` or `complete`. Maximum 8 KiB, unknown/duplicate fields rejected. The phase must match the route. Configured provider/installation binding is server-owned. `flowId` identifies the original verified recovery/reset flow for both phases; an unrelated later settings flow cannot replace it. The trusted integration must retain/resolve any recovery-to-settings association needed by the chosen provider sequence. Routine profile edits, anonymous email requests and browser redirects are not these events.

A 202 response contains only `operationId`, `eventKind`, `phase`, `recorded: true`. It acknowledges durable receipt, not provider cleanup success or product access. Use the existing safe problems for 401 invalid service credential, 409 conflicting/reordered evidence, 413 oversize, 422 invalid envelope/version/phase and 503 unconfirmed required dependency. Identity/flow mismatches return a safe 409 without target details. No callback error reflects the hook secret, body, cookies or provider text.

Derive the business event key from configured installation/provider, original flow, event kind and phase. The two phases bind to one original cleanup operation and one verified identity. A reused flow with a different identity/kind conflicts. A completion without its durable admission cannot create an obligation or clear a block: reject 409 and require reconciliation of the original admission. Concurrent repeats recover the one recorded acknowledgment. An already-completed duplicate returns that result without another native/broad Hydra revocation or a block release. Record event identity/evidence safely, not random delivery IDs as business identity and not proof credentials.

Access owns local blocking, the original durable obligation, independent provider outcomes and eligible release. The trusted Kratos integration owns verified reset evidence, ordered native cleanup and legitimate-session preservation. Its service-authenticated callback alone does not prove those outcomes. Admit must durably block before the pending cleanup interval can authorize product access. Confirmed native Kratos cleanup must precede trusted complete evidence; the worker then reconciles affected Hydra grants independently. Uncertain outcomes remain blocked, suspended users still need deliberate Restore users, and an older completion cannot release a newer block.

**#117 qualification gate:** demonstrate on selected pinned OSS releases that callback placement follows verified recovery/reset, admission failure prevents an unblocked reset, native cleanup preserves the legitimate new session, completion really follows confirmed native cleanup, changed recovery/settings flow IDs retain their original binding, and a lost callback/provider response can be reconciled without blanket revocation of later logins. Bound retries and persist unresolved obligations; exhausted reconciliation stays blocked and visible to host operations. Do not publish a guessed hook configuration or mark cleanup confirmed just because the generic webhook returned success. The inspected [Kratos v25.4.0 recovery webhook](https://raw.githubusercontent.com/ory/kratos/v25.4.0/selfservice/hook/web_hook.go) supplies flow/identity but does not add the recovery session to that hook's template context. This source observation is not runtime qualification. #117 must report an unsupported chosen placement as a contract conflict, rather than silently weakening the required block/evidence boundary.

<a id="review-and-remaining-work"></a>

## Reviewed scenarios and remaining #116 work

These are design-review scenarios, not executed tests:

| Scenario | Required outcome |
| --- | --- |
| SupportBot edits an existing Pipeline, then requests creation of another. | Permit the first with current Edit; deny resource creation in v1, regardless of an imported definition. |
| Application import needs a missing Collection or a changed immutable profile. | Reject the known-ineligible plan before writes; identify the human provisioning step, with no fallback identity. |
| Alice creates a Pipeline, loses the response and later loses an initial grant. | Recover the original result without recreating the removed grant or a second Pipeline. |
| SupportBot imports HR cases into the saved HRPrivate audience before source linking. | Store protected unreviewed content immediately; audience override is denied, linked sources later add checks. |
| Alice changes the import default from HRPrivate to SupportKnowledge. | Require Pipeline audience authority and management of both groups; existing cases retain HRPrivate. |
| The selected audience/reviewed revision changes before import or audience save. | Reject stale reviewed state; never widen or substitute the audience silently. |
| Alice loses assignment authority after issuing an invitation. | Activation fails current checks; an invitation is not a permanent authorization snapshot. |
| A user knows an unrelated trace, grant or invitation ID. | Apply current narrow visibility; no general audit/diagnostic browser follows from identifier knowledge. |
| Kratos cleanup succeeds but Hydra cleanup is uncertain. | Keep product blocked and reconcile the original operation without revoking later logins on duplicate completion. |
| A host repair uses a stale installation/responsibility revision. | Reject without partial assignments; a host token or target label alone is insufficient proof. |
| SupportBot sends a valid key to an ordinary human-only create operation versus the human-session check. | The ordinary operation returns 403 for principal eligibility; the identity-specific session check returns 401 for unsupported family. |
| A provider exceeds the remaining authentication budget. | Admit no late success or cached success; report unconfirmed verification without fallback. |
| Bob has verified Kratos identity but no local admission, and activates Alice's valid invitation. | Permit the narrow cookie/CSRF-protected admission operation, rechecking all issuer authority and recipient state. Scope preview alone creates no admission. |
| Key issuance succeeds but its secret-bearing response is lost. | Recover the same key metadata with `secretAvailable: false`; do not emit another key or cached plaintext. |
| A maintenance request or private callback exceeds its body bound or includes extra fields. | Reject before admitting effects, without reflecting protected input in the error. |
| Alice removes a use-only grant and a later grant is assigned before replay. | Replay the original removal outcome; do not remove the later assignment or encode absence as `canGrant: false`. |
| Alice creates a group with no stored document-action grant rows. | Her current manager relationship can administer its document-action assignments; she receives no automatic document-operation use. |
| SupportBot has budget inspection and Evaluation execution grants. | Permitted inspection/work does not permit human-only budget mutation or tracing administration. |
| Alice issues a multi-Project invitation while one reviewed Project revision changes. | Issuance conflicts atomically; activation later rechecks every intended current assignment authority, not historical revisions as authority. |
| Bob's invitation activation response is lost, then Alice leaves or the token expires. | Verified eligible Bob recovers the original completed activation safely; it does not consume again or recreate removed grants. |
| A different verified identity or a different key tries to consume an already used invitation. | Deny/conflict under the narrow activation contract; no second admission/assignment. |
| Bob previews an invitation, then Alice loses authority before activation. | The preview discloses only intended scope and has no effects; activation fails current checks atomically. |
| An invitation names only a group/action effect and Bob lacks Project membership. | Require an explicit Project-membership intent or an existing eligible relationship; safe 409, with no implicit membership or partial consumption. |
| Alice queries Project A's recipient directory with a target owned by Project B. | Reject the scope mismatch without exposing either directory; exact-target authority cannot cross-bind Projects. |
| Two key issuers see one usable key and race. | Coordinated commit admits at most one further usable key; no silent revocation to free a slot. |
| Maintenance proof expires after the original bootstrap response is lost. | A currently verified replacement token for the same subject may recover the original host operation; the token itself is not retained or fingerprinted as stable meaning. |
| A different candidate or responsibility reuses the host operation ID. | Fail `idempotency_key_reused`; no grants or identity-link replacement. |
| Private complete arrives before admission, or binds another identity to the flow. | Safe 409; no new obligation/block release; reconcile the original trusted admission. |
| A sole manager is suspended and provider cleanup fails. | Suspension succeeds without handover; access stays blocked and its original obligation persists. Restore cannot bypass incomplete cleanup or security review. |
| Project erasure is admitted while uploads/key issuance/publication race. | Coordinated project block fences new effects; shutdown precedes data erasure. Original eligible initiator's content-free status can survive membership removal. |

The 2026-10-04 approvals settle the catalogue, initial assignments, human-only provisioning with application updates, case audiences, invitations and diagnostic scope. They also settle session response fields/time budgets, authentication problem text/challenges, new Access mutation bounds, exact-action grant listing, invitation activation's admission boundary, key secret replay, the maintenance command/input bounds and the private recovery callback boundary.

The accepted proposal has now been expanded into concrete artifacts. The following review and handoff gates remain before declaring #116 complete:

| Remaining artifact | Required review/handoff |
| --- | --- |
| Complete Access operation matrix | Written in the [HTTP draft](#http-operation-matrix), including preserved symbols, new target-specific operations, credential/status/revision/visibility profiles and bounded fields. Final written-contract review must accept the new symbols and field details. Domain-owned deletion/status schemas remain explicitly with #124/#38/#204. |
| Maintenance proof and versioned models | Written in the [maintenance draft](#maintenance-wire), using transient Hydra access-token identity proof through protected stdin. Review the exact versioned models, replay/error semantics and installation identity; #27/#117 implement and qualify them. |
| Recovery integration handoff | Written in the [private callback draft](#recovery-wire). Review original-flow binding, acknowledgment and safe failures. #117 must qualify actual hook ordering, durable admission and reconciliation, native-completion evidence and legitimate-session preservation; unqualified YAML is not a #116 deliverable. |
| Closure review | The read-only spec review is complete with no remaining blocking findings. Obtain final maintainer acceptance of this engineering draft. Reconcile GitHub bodies/checklists in a separately authorized update. The live #116 body inspected on 2026-10-04 still contains seven-grant requirements; [ADR-0059](../adr/ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md) and the seventeen-grant contract supersede those requirements. Preserve their historical evidence when reconciling. |

No GitHub issue is edited or closed by this documentation update.

Full domain schemas and runtime qualification remain with the consuming specification/implementation issues, including #117/#30 identity/credentials, #121 model contracts, #128 Pipelines, #147 tracing and #151 portability. Pinned provider compatibility and browser/CLI/OS tests are delivery evidence, not something this decision capture supplies. [CLI delivery](cli-delivery-plan.md) owns that traceability.

## Decisions

- [ADR-0059](../adr/ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md): fixed creator initialization, superseding the eleven-action Project seed.
- [ADR-0060](../adr/ADR-0060-keep-v1-resource-provisioning-human-only.md): human resource provisioning with application-driven operations/updates.
- [ADR-0061](../adr/ADR-0061-control-evaluation-audiences-through-pipeline-authority.md): human Pipeline-scoped case-audience administration and protected import defaults.
- [ADR-0062](../adr/ADR-0062-activate-invitations-under-current-issuer-authority.md): single-use invitation activation under current authority.
- [ADR-0063](../adr/ADR-0063-defer-product-non-query-diagnostic-browsing.md): v1 non-query diagnostic browsing deferral.
