# Administer an exact action grant

<a id="administer-an-exact-action-grant"></a>

Alice gives Bob use-only permission on Support. A grant names one recipient, action and exact target. The write checks current authority, recognizes a retry, applies its revision guard and saves the change with audit.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="storing-access-and-handling-simultaneous-changes"></a>

## Choose a focused reading task

- For exact target-specific HTTP fields, read [Grant contracts](grant-contracts.md).
- For shared nested target variants, read [Grant target contract](grant-target-contract.md).

## Storing access and handling simultaneous changes

The database keeps identity, membership, permissions, and history separate because they change for different reasons. Replacing a key should not recreate permissions. Rejoining a project should not restore removed access. An old audit entry should never authorize a new request.

<a id="separate-records-explain-separate-responsibilities"></a>

### Separate records explain separate responsibilities

The arrows below show relationships between records, not calls between services. The diagram groups similar concepts for readability. It does not propose one generic grants table or a generic resource registry.

```mermaid
---
title: "Project grant, membership and document audience relationships"
---
flowchart TB
    Principal["Principal<br/>Human or application identity"]
    Principal -->|"belongs through"| Membership["Project membership"]
    Principal -->|"receives"| Grant["Action permission<br/>May use, or use and grant"]
    Grant -->|"applies to"| Target["One exact resource"]
    Membership -->|"required for"| Audience["Group membership<br/>May read shared documents"]
    Audience -->|"required for eligible humans to hold"| Manager["Group management<br/>May share access"]
    Audience -->|"joins"| Group["Group within one project"]
    Manager -->|"manages"| Group
    Document["Document"] -->|"lists allowed groups"| Group
```

The `application_accounts` record extends a principal with its one owning project. It shares the principal ID and the same permission model. Creation saves the principal, account, project membership, creator grants, and audit together.

Every manager record needs a membership in that same group and project. Appointment, demotion, and removal must preserve this relationship. The [14-table Access foundation](access-persistence.md#proposed-access-foundation-table-map) is created by the initial migration. It has a foreign key from each manager assignment to the matching group membership, plus human-only and same-project checks. PostgreSQL integration tests prove that a manager without matching membership or a non-human manager is rejected. The migration does not implement appointment, handover, or recovery workflows.

<a id="one-current-assignment-per-permission"></a>

### One current assignment per permission

There is one current grant per **recipient + action + exact target**. Its `can_grant` field is `false` for use-only, not an explicit denial, or `true` for use-and-grant. Applications cannot hold `true`. Another authorized person changes this same assignment rather than creating a duplicate.

Code defines the supported actions, targets, eligible recipient types, and fixed rules such as Edit including View. Unknown actions are denied. Included View access needs no extra grant row or configurable role language.

Grant tables are divided by target type, not by action: organization, project, group, application, and later real Pipelines and Deployments. Database relationships check the target and project, rather than trusting an unchecked `resource_type + resource_id` pair. Later domain tables arrive with their features, not as placeholders.

For example, these are three different relationships:

| Relationship | What it means |
| --- | --- |
| Alice may issue SupportBot keys. | Alice has an administration grant over the application. |
| SupportBot may query Production. | The bot has an action grant on a Deployment. |
| SupportBot belongs to SupportKnowledge. | The bot has group membership for document access. |

<a id="keep-current-access-separate-from-history"></a>

### Keep current access separate from history

Revoking a grant deletes its current row. Downgrading changes its level. Giving it back later creates a fresh assignment, rather than reviving an inactive row or reading permission from history. Suspension is different because the assignments remain while account status prevents their use.

Each change and its audit event are saved in the **same transaction**, meaning either both succeed or neither does. Audit records who changed what, using limited, safe before-and-after values. They exclude secrets, key verifiers, sessions, document text, and whole permission snapshots. Operator and initial-setup events identify their real actor rather than inventing a human account. Audit history has its own access and erasure rules.

The exact Project grant service owns a short transaction through `TransactionManager`. It reads current management facts under compatible coordination and applies the existing eligibility, visibility and delegation policies before reservation or replay. [The implemented request chain](../../inframeld-python-standards/references/services-and-use-cases.md#grant-command-flow) follows the flat PUT/DELETE Commands, static HTTP mapper, aggregate transition and original-result persistence. Fresh changes save the grant, one revision increment, required audit and immutable business receipt together. An authorized no-op records its original outcome without another revision or change audit. A replay returns that original receipt without reapplying later state. The concrete Organization, access-group and application-account services follow their own exact target contracts and coordination. [Their persistence](access-persistence.md#access-action-grant-results) remains distinct from live assignments.

Database constraints reject duplicate and cross-project records. A Support grant cannot name a Finance Deployment, and SupportBot cannot join another project. They also block deletion of a parent record while live relationships depend on it. Application logic checks who may make the change, arranges required handover, and removes dependencies deliberately. Automatic deletion of related database rows cannot replace those steps.

<a id="alice-and-bob-both-try-to-leave"></a>

### Alice and Bob both try to leave

Suppose Alice and Bob are the only people who can grant Manage releases on Production. If their removal requests run independently, each could see the other still present and both could leave. Support would then have nobody able to grant that permission.

The backend prevents this by making access changes within a project **take turns**. It checks the current state when each change gets its turn, not only when the request first arrives.

```mermaid
---
title: "Accepted coordination of competing access changes"
---
sequenceDiagram
    participant Alice as Alice's change
    participant DB as PostgreSQL
    participant Bob as Bob's change

    Alice->>DB: Request a turn to change Support's access
    Bob->>DB: Request a turn to change Support's access
    Note over DB,Bob: Bob waits while Alice's change finishes
    Alice->>DB: Check current permissions<br/>and that Bob can remain responsible
    Alice->>DB: Save removal, change number and audit
    DB-->>Alice: Saved
    DB-->>Bob: Now check against the updated records
    Bob->>DB: Check who would remain
    DB-->>Bob: Reject an outdated request<br/>or removal of the last grantor
```

A **revision** is the change number for an organization or project. Where a request must include its expected revision, the backend compares that number with the current one before saving. An old form cannot overwrite newer decisions, even if a permission was removed and regranted with the same recipient, action, and target. Revisions follow the [shared exact numeric range and exhaustion rules](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md#numeric-revisions). A revision detects outdated requests. It is not a saved permission set that can authorize future work. Retries follow the [idempotency and conflict rules](../../inframeld-application-contracts/references/idempotency-and-replay.md#revisions), not an unconditional overwrite.

This protection applies whenever access or its dependencies change: initial setup, permissions, member removal, recovery, key creation or revocation, group references, and deletion. For example, two people creating keys at once must not exceed the two-key limit. The backend checks the issuer's full current authority and counts usable keys in the same turn. Likewise, a group cannot be deleted while another change adds a reference to it.

<a id="how-the-database-gives-each-change-its-turn"></a>

### How the database gives each change its turn

A database **lock** makes conflicting changes wait. The accepted design calls for this order:

| Change | Locks to take |
| --- | --- |
| Project access change | First a shared lock on the organization row, then an exclusive lock on the project row. Shared organization locks allow different projects to change at once. The exclusive project lock makes changes in that project take turns. |
| Installation permission or account-status change | An exclusive organization-row lock. This makes a suspension and affected project administration wait for each other. |
| Change involving multiple projects | Take the organization lock first, then project locks in stable ID order. Limit waiting time and handle transaction failures. |
| First local admission, recovery admission/completion or credential-state initialization | Under accepted ADR-0082, acquire the exact identity's transaction-scoped advisory lock before any required organization/project locks, then reread current facts. Recovery admission/completion and initialization implement this prerequisite. First admission remains future work. Follow [identity coordination](identity-admission-coordination.md). |

While holding the required locks, the backend checks current permissions and whether the accounts and resources still allow the change. It checks the expected revision where required, applies the change, increments the revision, and saves the audit event in one short transaction. Every path listed above must follow compatible locking rules, including recovery and deletion.

Ordinary permission reads do not take these exclusive administration locks. **Never keep an access-change transaction open while waiting for an upload, a user, Kratos, or a model call.** Checks before sending work or returning protected content still happen where needed, outside this transaction.

Finer locks for individual resources and serializable transactions, an alternative way to coordinate database work, were considered and deferred. Start with queries limited to the relevant project, useful existing primary and unique indexes, and document checks performed in batches. Measure query plans and waiting between changes before adding caches or finer locks. The design alone promises no particular capacity. [ADR-0022](../../../../docs/adr/ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md) records the choice.

<a id="grant-management"></a>

<a id="exact-grant-management-and-bounded-reads"></a>

## Exact grant management and bounded reads

The live mutation interface is exact-target PUT/DELETE. `POST /v1/projects/{project_id}/grants` now returns 405, including an old body without a GET query. Its operation, creation-only Command and generated request/response exports are retired under [ADR-0128](../../../../docs/adr/ADR-0128-consolidate-exact-target-grant-mutations.md). Current callers explicitly choose PUT intent. Retained historical POST metadata keeps its original literal route, method, actor, key, fingerprint, expiry and outcome. Read-only lookup never redirects or redispatches it as PUT.

The [Project action-grant reader](../../../../apps/backend/src/inframeld_backend/access/http/routes/project_action_grant_routes.py) implements `GET /v1/projects/{project_id}/grants`, operation `listProjectActionGrants`. It requires one supported Project `actionId` and a current eligible human Project member with exact use-and-grant authority on every page. Use-only permission and the group-manager document-action alternative do not authorize this Project read. The bounded page reports only stored assignments, including suspended recipients, with flat `projectId`, `recipientPrincipalId`, `actionId` and `canGrant` fields, plus nullable `nextCursor`. It supplies no effective-permission expansion, eligible-recipient directory, totals or Access revision. No body, expected revision or idempotency key applies. Responses are no-store.

The [grant-list guide](../../../../apps/docs/src/app/guides/list-project-action-grants/page.mdx) explains that unchanged read. The Project component also implements [`getMyProjectAccess`, `setProjectActionGrant` and `removeProjectActionGrant`](grant-contracts.md#implemented-project-grant-administration). The own-access read supplies the caller's current reviewed Project Access revision without requiring broader administration authority. The [assignment guide](../../../../apps/docs/src/app/guides/assign-project-grant/page.mdx) covers all eighteen Project actions, strict PUT JSON, bodyless DELETE with its revision query, immutable original results, safe last-grantor checks and read-only recovery of retained historical POST metadata. Native OpenAPI and generated clients define the delivered shapes. Source and database checks do not establish final native SDK/platform qualification or human acceptance. [Human qualification #336](https://github.com/matejpalenik/inframeld/issues/336) retains manual preparation, dry run and execution for pre-v1 testing. Source implementation does not establish those results or full issue completion.

[#226](https://github.com/matejpalenik/inframeld/issues/226) owns complete Organization, Project, access-group and application-account grant administration and the supporting Access reads. Access continues to own the common grant rules for every target. Each other resource feature owns delivery of its real target tables and concrete grant integration, including target-specific routes and recipient discovery under these rules. Those integrations remain required v1 work. They do not require placeholder resources or prevent Access-owned administration from completing. [The transport boundary](grant-contracts.md#grant-delivery-boundary-and-cutover) distinguishes the accepted target catalogue from delivery ownership.

Full assignment, downgrade and removal identify the exact target, recipient and fixed action, and carry the expected access revision. Assignment/downgrade explicitly state `canGrant` as a boolean. An application recipient may receive only an eligible use-only assignment. Every management operation requires an eligible human with current can-use-and-grant for that exact action/target, or the existing group-manager authority for document-action assignments on that group, and retains scope, last-administrator and current-state checks. Reject unsupported action/target/recipient combinations rather than storing an unusable grant.

Original grant-operation lookup retains current eligible-human can-use-and-grant authority for the original exact target/action. For an original POST grant this is `create-access-groups` on the original Project, including after route retirement. It discloses only permitted retained operation metadata, without reapplying assignment-time recipient eligibility or expected revision. Preserve the original method, canonical route, fingerprint, expiry and outcome under their existing retention. A caller-supplied lookup guard cannot downgrade this authority. Missing or uncertain evidence cannot establish failure or justify a fresh PUT. This read never redispatches the original write.

List assignments for one exact target and required `actionId`, with current can-use-and-grant for that action or the existing current group-manager authority for document-action assignments on that group. Use the [existing bounded pagination contract](../../inframeld-application-contracts/references/pagination.md): default 25, maximum 100, stable recipient-ID order and current authority on every page. Do not broaden this into a project-wide administrator inventory. Mutation results describe the original committed change and access revision. Use a fresh authorized read to learn the current assignment. The [concrete contracts and future-resource drafts](grant-contracts.md#http-operation-matrix) specifies routes, operation IDs and request/result models for final review.

<a id="operation-contracts"></a>

<a id="application-operation-inputs-results-and-failures"></a>

## Application operation inputs, results and failures

The following are semantic application contracts, not new published DTO/class names or final JSON field spellings. Inputs use application-owned typed IDs and verified caller context. Each operation checks current authority itself. A review by a client does not authorize a later save.

| Operation family and owner | Required input | Result and failure behavior |
| --- | --- | --- |
| Resource creation , owning domain with Access initialization | Verified human caller, exact parent Project/Organization, typed definition and original operation identity | Resource ID plus committed initial assignments/outcome. Deny application callers. Reject unavailable names/invalid dependencies. Original replay cannot recreate grants. |
| Configuration/membership update , resource owner | Verified caller, exact resource ID, supported change, reviewed expected revision and original operation | New committed revision or original outcome. Stale state conflicts. Wrong action/kind denies. Immutable meaning is never overwritten. |
| Grant administration , Access | Verified human, recipient ID/kind, fixed action/exact target, level and expected access revision | Exact committed assignment/removal and revision. Deny unsupported combinations, missing delegation or stranded ordinary handover. Reads reveal only assignments the caller may administer. |
| Case/import audience change , Evaluation with Access | Verified human, Pipeline ID, explicit case selections or future-import setting, authoritative old/proposed group IDs and expected revisions | Saved audience/revision, audit and bounded outcome. Deny missing Pipeline action or any old/new group management. Stale selection conflicts. [Evaluation](../../inframeld-evaluation/references/case-audiences.md#case-audiences) owns the full contract. |
| Case import , Evaluation | Verified caller, Pipeline ID, protected content/identity/provenance, reviewed destination audience/revision and verified optional source mappings | Protected cases/revisions, reused/changed/unresolved outcomes. Changed content is unreviewed. An application uses the saved human-approved audience and cannot override it. |
| Invitation issue/revoke/activate , Access with Ory boundary | Exact intended assignments, verified issuer/recipient identity as appropriate, bounded secret/lifetime, expected state and original operation | Safe invitation/activation outcome. Issuance delivers its secret once. Expired/revoked/used/stale/ineligible intent cannot assign. Recover original activation after response loss. |
| Identity recovery cleanup , Access with identity adapters | Authenticated server-side, flow-bound evidence. Stable subject/principal. Original operation. Independent provider outcome evidence | Temporary product block and durable Kratos/Hydra obligations. Uncertain cleanup stays blocked. Completed duplicates initiate no new cleanup. An unfinished bulk attempt may revoke newer CLI credentials. An older flow cannot release a newer obligation. |
| Project deletion/status , Access and owning cleanup workflows | Verified human, exact Project, original operation and reviewed state | Immediate block and durable shutdown/erasure. Narrow content-free original-operation status can survive membership removal. No private content in status. |
| Host bootstrap/stranded repair , Access maintenance boundary | Protected versioned host input, verified installation and Ory identity, exact expected responsibility/revision, operator/reason and original operation | Narrow assignment plus audit/revision or conflict. No ordinary product bearer authority or global administrative bypass. |

Identity/credential failures, permission denial, hidden-resource 404, stale state and retry conflicts retain the [existing problem contract](../../../../docs/development/error-handling.md#authentication-contract). Do not relabel provider unavailability as invalid credentials or lost permission as empty data. Secret-bearing operations retain [show-once recovery](application-keys.md#secrets). Paid work uses ordinary admission and uncertain-dispatch rules, not blind retries.
