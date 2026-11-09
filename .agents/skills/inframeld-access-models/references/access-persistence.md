# Access persistence: scoped relationships and current assignments

Alice gives SupportBot Query on Production. PostgreSQL must retain the real principal, the right Project membership and one exact assignment. It must not accept a grant bound to Finance or turn an audit event into current permission.

**Status:** the initial migration implements the fourteen-table Access foundation. Later-feature relationships below are explicitly proposed integration points. Migrations own exact delivered columns and constraints. Application policy still owns current eligibility and permission decisions. This is a persistence reference, not an administration workflow or an instruction to create future tables now.

## Read the relevant part

- For relationship checks, use [Database constraints and application decisions](#use-database-constraints-for-relationships-and-application-policy-for-decisions).
- For the delivered foundation, use [Identity and membership tables](#identity-ownership-and-membership-tables), [grant tables](#current-action-grant-tables) and [audit](#audit-table).
- For future resources, use [Integration points](#tables-integrated-with-later-features). Proposed rows are not implemented schemas.
- For exact code authority and limits, use [Implementation boundary](#implementation-boundary) and [the migrations](#implemented-persistence-authority).
- For ordered writes, use [Lifecycle persistence](access-lifecycle-persistence.md). For domain objects, use [Implemented models](implemented-access-models.md).

<a id="proposed-access-foundation-table-map"></a>

<a id="access-foundation-table-map"></a>

## Access foundation table map

**Status:** The application-account extension and write coordination were accepted on 24 September 2026. The initial migration now implements the 14 foundation tables and their core keys and relationships. The two accepted choices are:

1. Keep `application_accounts` as a small extension of the shared principal. Enforce its one owning project in membership relationships.
2. Protect Access writes with short project-scoped transactions, the [organization/project lock protocol](grant-administration.md#storing-access-and-handling-simultaneous-changes), and revisions that reject stale administration changes. Finer locks are deferred unless measured contention justifies them.

The map below describes the implemented foundation and its later integration points. Exact action IDs are not yet enforced by database checks. Audit payload limits, retention, and index needs still require implementation review. This is not the complete schema for the application.

There are **14 foundation tables**, mostly small relationship tables. They belong to one Access module in one PostgreSQL database. They do not require 14 services, repositories, or aggregates. Keys, Documents, Pipelines, and Deployments arrive with their own features.

<a id="use-database-constraints-for-relationships-and-application-policy-for-decisions"></a>

## Use database constraints for relationships and application policy for decisions

A foreign key must establish both that a referenced object exists and that it belongs to the right organization or project.

For example, a Support group membership references a group in Support and the principal's Support membership. A Support grant cannot target a Finance Deployment. A Document cannot name another project's group. Add equivalent constraints when each resource is introduced. Do not create placeholder Documents or Deployments before their owning features define them.

Use a foreign key containing both project ID and resource ID to check their relationship. [PostgreSQL supports multi-column foreign keys](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-FK). Keep the accepted target-specific grant tables and real references, rather than introducing a generic resource registry.

Unique constraints prevent ambiguous identity links and duplicate membership, manager, or recipient/action/target rows. Revocation removes current rows while history stays separate, so readmission cannot accidentally restore old authority. Review further keys, indexes, delete behavior, and audit details against each lifecycle.

Database constraints and application policy answer different questions. Foreign keys can check Alice's group and project relationships. They cannot establish that she is unsuspended, may grant this permission, or leaves another active grantor. The application must check those conditions while protecting the change against concurrent writes. A row `CHECK` is not suitable for enforcing conditions involving other rows.

<a id="column-conventions"></a>

## Column conventions

- Use stable UUIDs, PostgreSQL `timestamptz` for times, and a required boolean `can_grant`. Display names are editable labels, not permission keys, and need not be unique. Resource-name uniqueness follows the [defined scope](../../inframeld-architecture/references/resource-names-and-identity.md#resource-naming), not a global namespace across all resource types. Never infer membership from either value.
- Organization/project ownership is required and immutable on live records. Foreign-key columns for current memberships, targets, and recipients are non-null unless a conditional relationship below explicitly allows null. Scoped references require real composite unique keys, as defined by the migrations for implemented tables. Preserve that requirement when adding future relationships.
- Restrict principal kind to `human` or `application`. If another table repeats that kind for a constraint, a foreign key must verify it against the principal's actual kind. Callers cannot choose the copy, and kind changes are unsupported.
- Principals accept `active`, `suspended`, and `retired`. Projects accept `active` and `deleting`. Database checks restrict stored values, while application logic must still enforce valid transitions. Application retirement is terminal, and retaining its row never makes its keys valid.
- Assignments record `assigned_at` and nullable `assigned_by_principal_id`. The latter records attribution, not continuing authority. Reference the stable principal without cascading deletion, and allow null under authorized erasure. Audit operator/bootstrap activity explicitly. Nullable attribution does not permit an ordinary caller to skip verified attribution.
- Organizations and projects have a nonnegative integer `access_revision`, stored in a PostgreSQL `BIGINT` with the [shared numeric revision bounds](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md#numeric-revisions). Advance the relevant scope's revision for each committed Access administration change. Reject an exhausted changed write atomically instead of wrapping the revision. Administration requests carry the expected revision so stale changes are rejected, including removal followed by regrant. It is not a cached permission snapshot. A project change does not advance every other project's revision. The administration contract owns its request/response representation.

<a id="identity-ownership-and-membership-tables"></a>

## Identity, ownership, and membership tables

Column spellings here describe the current Access foundation, not a completed implementation of the [resource-naming convention](../../inframeld-architecture/references/resource-names-and-identity.md#resource-naming). In particular, existing text `name` columns must not be mistaken for the new distinct selector/display-name contract.

A primary key (`PK`) uniquely identifies a row. A foreign key (`FK`) requires a matching referenced row. A `unique` constraint prevents duplicate values in its named column set. Add timestamps or display fields only when a workflow needs them.

For each table's exact columns, primary keys and unique constraints, read [the implemented migration](../../../../apps/backend/migrations/versions/0001_initial.py). The following table explains their purpose rather than maintaining another schema.

| Table | Meaning and required relationship |
| --- | --- |
| `organizations` | One installation organization is provisioned in v1. No multi-organization administration follows from having this table. |
| `principals` | FK to organization. Stable identity shared by human and application authorization. A local admitted human is represented here. An unverified login or pending invitation does not create an active principal. Status is checked whenever authority is evaluated. |
| `human_identity_links` | FK `(organization_id, principal_id, principal_kind)` to principal. The verified identity pair maps to exactly one local human. The link uses the verified Kratos identity source/ID. No email-based merging. This shape does not enable self-service identity linking. |
| `projects` | FK to organization. Deletion first marks the project unavailable and starts the accepted cleanup lifecycle. No stored creator or owner field supplies implicit authority. |
| `application_accounts` | FK `(organization_id, principal_id, principal_kind)` to principal and `(organization_id, project_id)` to project. Records the application's one immutable owning project. Its ID is the shared principal ID, not a second identity. Contains no permissions or credential secret. |
| `project_memberships` | FK `(organization_id, project_id)` to project and `(organization_id, principal_id, principal_kind)` to principal. The conditional application FK described below prevents admitting a bot to another project. Membership gives no operational or document permission. |
| `access_groups` | FK to project. A document audience. No nested groups or role bundle. Management is recorded separately. |
| `group_memberships` | FK `(project_id, group_id)` to group and `(project_id, principal_id)` to project membership. This is the principal's group-based document audience, not an operational grant. |
| `group_managers` | FK `(project_id, group_id)` to group and `(project_id, principal_id, principal_kind)` to project membership. Also FK `(project_id, group_id, principal_id)` to `group_memberships`, with restricted parent deletion. Every manager requires matching ordinary membership. Reads use membership rather than a manager bypass. |

**One application, one project:** for a human membership, `application_principal_id` must be null. For an application membership, it must be non-null and equal `principal_id`. Enforce that distinction with a row check, then add FK `(project_id, application_principal_id)` to `application_accounts(project_id, principal_id)`.

The repeated ID lets PostgreSQL check that an application joins only its owning project while humans can join several. It is not a second application identity. A nullable foreign key without the kind/nullability check would let an application evade this check.

Create the principal, application account, project membership, creator administration grants, and audit event together. The account is usable only while its principal, account, project, and membership satisfy current policy.

Keeping the owning-project reference separate from membership lets retirement remove membership while retaining an inactive account reference for history. Historical or incomplete records do not authorize work.

A separate human-profile table is unnecessary until Inframeld needs human-only application data. Kratos owns passwords and sessions.

## Application creation, names and key metadata

[Migration 0024](../../../../apps/backend/migrations/versions/0024_application_accounts.py) extends the existing account row with a nullable `resource_name`. Existing principal Display names remain unchanged, and migration invents no selector. New names are unique per Project and application-account type. The principal-kind and scoped membership foreign keys bind the account to its one Project. Application memberships must carry the non-null matching application principal ID, so SQL null semantics cannot bypass that foreign key. Human memberships retain a null application binding.

| Table | Implemented purpose |
| --- | --- |
| `application_account_name_reservations` | Reserve an exact Project-scoped Name for its original principal, with its authoritative Organization/Project/account foreign key. A retired reservation cannot be overwritten by another creation. |
| `application_account_creation_results` | Retain original account ID, creator, names, before/after revisions and exactly three fixed creator actions. Its foreign key binds the Project-scoped reservation, Organization and actor. Deleting expired reservation history removes this result without releasing the separate Name reservation. |
| `application_keys` | Store key UUID, exact account/Project/Organization and installation bindings, fixed nullable HTTP/MCP audience slots, nonempty unique supported adapter array, SHA-256 verifier bytes and safe issuance/expiry/revocation metadata. Verifiers are excluded from row representations and the authorized read projection. No plaintext is stored. The [key contract](application-key-contracts.md) owns verifier format and lifetimes, and its [currentness contract](application-key-contracts.md#verification-results-and-unresolved-currentness) owns authentication checkpoints. Issuance still enforces the two-usable-key limit separately, without per-key grants. |

Creation results require a single revision increment within the [shared safe revision bound](../../../../docs/adr/ADR-0129-bound-numeric-revisions-to-the-javascript-safe-integer-range.md) and the fixed three initial actions. Credential checks constrain digest length, adapter alternatives and lifecycle order, with an account/UUID index for bounded key reads. The creation/metadata records do not themselves perform issuance or authentication. Their separate services own current authority and coordination. Issuance adds the two-usable-parent-key guard and atomic credential/original write. Individual revocation adds the separate result below, while account retirement retains its own obligations.

[Migration 0028](../../../../apps/backend/migrations/versions/0028_application_key_issuance.py) replaces the single audience with nullable `http_audience` and `mcp_audience` slots. Its SQL requires non-null, nonblank selected slots and NULL unselected slots without accepting a NULL-unknown CHECK result. It copies each legacy audience literally into its already-selected slots, preserving adapter order, identity, verifier and lifecycle. It never populates old rows from current profiles or expands their authority. One parent key counts once across adapters.

The same migration adds `application_key_issuance_results` for immutable safe original metadata, separate from the secret-bearing first response. Scope/actor/account/operation constraints retain its original binding and contain no plaintext or verifier. Downgrade refuses retained issuance originals before dropping their table. Restoring the single-audience representation is lossless only for single-adapter and equal dual bindings. It refuses every unequal dual binding, including expired or revoked keys, before destructive changes. The selected generated clients cover the implemented contract. Deployment qualification remains separate.

[Migration 0029](../../../../apps/backend/migrations/versions/0029_application_key_revocation.py), following 0028, adds `application_key_revocation_results`. Its original operation foreign key binds actor, Organization and Project. Separate account and installation foreign keys retain the target scope. Safe key identity, adapter order and lifecycle timestamps are captured without a mutable-key foreign key, secret, verifier or audience values. Constraints require a non-null revocation timestamp, valid lifecycle order and a bounded revision delta of zero or one. A zero delta represents a fresh already-revoked no-op.

The [writer](../../../../apps/backend/src/inframeld_backend/access/infrastructure/writers/postgres_application_key_revocation_writer.py) retains current human Revoke authority and Project coordination. First revocation changes only the selected parent key, advances the Project revision once and saves its audit and original in the same transaction. A fresh no-op saves only its original, and exact completed replay returns the retained original without another write. The downgrade refuses to discard any retained revocation originals before dropping their table. The implemented schema does not mean retained installations have already upgraded. Apply the [required schema](../../../../docs/development/getting-started/local-setup.md#migrations) deliberately before starting compatible processes.

The creation writer retains all existing Project coordination and conditional revision guards. Principal, extension, membership, creator assignments, audit and completion commit together. Downgrade refuses to discard retained new account outcomes, Name reservations or credentials. An empty extension migration remains reversible and preserves legacy labels and identities.

## Access-group names and original administration results

[Migration 0025](../../../../apps/backend/migrations/versions/0025_access_group_administration.py) adds nullable `access_groups.resource_name` without changing legacy `name` Display names. Named groups reference their exact Project/Name/group-ID binding. Legacy groups remain addressable by ID with a null Name.

| Table | Implemented purpose |
| --- | --- |
| `access_group_name_reservations` | Keep an exact Name bound to its original group ID and Organization/Project scope. Physical group deletion retires the binding rather than freeing the Name. |
| `access_group_creation_results` | Keep original names, creator, group ID and revisions independently of later removable memberships or the group row. |
| `access_group_relationship_results` | Keep the exact member/manager transition, changed flag, original HTTP status and before/after revisions. Foreign keys bind the original operation scope. Checks preserve management as a membership subset and unchanged revisions for no-ops. |
| `access_group_deletion_results` | Keep the original ordinary deletion receipt without retaining a live group or phantom manager. |

Expired ordinary reservations may remove their business results. They do not remove permanent Name bindings or the separately retained deletion binding and owner observation. [Operation recovery](../../inframeld-application-contracts/references/operation-recovery-contracts.md#access-group-deletion-recovery) owns that initiator-only projection and its captured expiry. Downgrade refuses retained group identities, administration results or group-deletion status bindings, including unnamed legacy groups whose ordinary operation history has already expired.

Current group deletion removes real manager, member and group-action-grant rows in dependency order. Document, source, active-upload, default and case producers are absent from the current schema. Their owning features must add actual scoped restrictive references and compatible coordination. No placeholder owners or reference registry represents those future integrations.

<a id="organize-grant-tables-by-target-type"></a>

## Organize grant tables by target type

The accepted 24 September 2026 design uses **separate grant tables for organization, project, group, and each supported resource target type**. Query and Manage releases on Deployments share a Deployment-grants table. It is not one table per action, recipient, or individual Deployment.

Each grant table refers to its real target and owning scope using foreign keys. Add Pipeline and Deployment grant tables with their owning features, alongside the actual resources. Organization grants refer directly to the organization without inventing a project. The Access foundation does not create placeholder domain resources for future permissions.

All these tables use the same permission rules and two grant levels. Separate tables do not require separate evaluators, services, or a repository class for each table. Exact names and columns still need implementation review.

<a id="current-action-grant-tables"></a>

## Current action-grant tables

Original-request lookup reads these current grants to authorize its expected guard independently of reservation existence. Organization lookup uses the existing exact Organization grant and current eligible human in that Organization, without inventing a Project. Retained authority family/action on a reservation is historical matching metadata, never a grant or permission snapshot. The [lookup contract](../../inframeld-application-contracts/references/operation-recovery-contracts.md#original-request-lookup) owns supported families and legacy failure handling.

Every grant row contains `recipient_principal_id`, `recipient_kind`, `action`, `can_grant`, and assignment attribution. `action` is a stable identifier defined in code. Row checks restrict actions and recipient kinds to the supported catalogue as it is implemented.

An application's `can_grant` must be `false`. The recipient-kind foreign key prevents treating it as human. Application policy also denies unknown or unsupported actions, even if an unexpected value appears in storage.

The foundation grant tables use recipient, action and exact target together as their primary key. Future target tables follow that accepted identity rule as their owning feature is implemented. A separate grant ID is unnecessary. Scope revisions detect stale changes even when removal and regrant create the same key again. Follow the [request retry rules](../../inframeld-application-contracts/references/idempotency-and-replay.md#requests) and [Access expected-revision checks](grant-administration.md#storing-access-and-handling-simultaneous-changes). An unconditional upsert must not overwrite another change silently.

| Table | Primary key / exact assignment | Required foreign keys |
| --- | --- | --- |
| `organization_action_grants` | `(organization_id, recipient_principal_id, action)`. | `(organization_id, recipient_principal_id, recipient_kind)` to principal. Currently accepted installation actions are human-only. Constrain the kind accordingly. No artificial project is needed. |
| `project_action_grants` | `(project_id, recipient_principal_id, action)`. | `(project_id, recipient_principal_id, recipient_kind)` to project membership, plus project target. Enforce the catalogue's human-only administration restrictions. |
| `group_action_grants` | `(project_id, group_id, recipient_principal_id, action)`. | `(project_id, group_id)` to group and `(project_id, recipient_principal_id, recipient_kind)` to project membership. Supports the accepted Add/Update/Delete documents permissions on groups. Ordinary group membership remains a separate fact. |
| `application_action_grants` | `(project_id, application_principal_id, recipient_principal_id, action)`. | `(project_id, application_principal_id)` to application account and `(project_id, recipient_principal_id, recipient_kind)` to project membership. Recipient kind is human. These are Issue keys, Revoke keys, and Delete application account permissions **over the application**, not the permissions the bot uses. |

For example, Alice's permission to issue SupportBot's keys belongs in `application_action_grants`. SupportBot's permission to query Production belongs in the future `deployment_action_grants`. SupportBot's access to the Support-documents audience belongs in `group_memberships`. These three records have different purposes.

<a id="access-action-grant-results"></a>

## Original exact action-grant results

[0026_access_action_grant_results](../../../../apps/backend/migrations/versions/0026_access_action_grant_results.py) adds three concrete result tables: `organization_action_grant_operation_results`, `group_action_grant_operation_results` and `application_action_grant_operation_results`. They retain the original target, recipient, method, level/removal meaning, HTTP status, changed flag and revision alongside the existing operation binding. Project grants retain their already implemented result table.

These are historical receipts, not live assignments or authority. They survive later membership or grant removal through their original operation lifetime. A replay validates the retained actor, exact scope, method, action and business result before returning it. Fresh changes save grant, one revision increment, required audit and original result atomically. No-ops record the original unchanged revision without a change audit. Downgrade refuses to discard these retained result rows. [Grant administration](grant-administration.md#exact-grant-management-and-bounded-reads) owns current permission, recipient eligibility and handover checks.

<a id="audit-table"></a>

## Audit table

The four grant tables plus the nine identity/membership tables and this audit table make the 14-table foundation.

| Table | Core fields | Boundary |
| --- | --- | --- |
| `access_audit_events` | `id` PK, `occurred_at`, `organization_id`, nullable `project_id`, `actor_kind`, nullable `actor_principal_id`, nullable operator/bootstrap `actor_reference`, nullable affected principal, `event_type`, `target_kind`, stable `target_id`, nullable action, JSONB `before_values` and `after_values`, nullable reason and `correlation_id`. | A bounded historical record of an Access change. Write it in the same transaction as the state change. Normal APIs cannot edit history, but authorized retention/erasure still applies. It is never queried to grant access. |

Audit records preserve historical identity and scope. Do not cascade their foreign keys to current grants, memberships, groups, or resources. Otherwise deleting a permission could erase its own evidence or become impossible.

A target kind and ID are suitable in history because they are not used to authorize access. Validate each event and limit its safe before/after payload. Do not copy entire domain objects, permission snapshots, document text, keys, hashes, or session data. Operator/bootstrap events do not need a fake human principal. Their authenticated maintenance path supplies the actor reference and required reason.

The audit table's existence does not grant anyone audit-reading rights or promise permanent retention. Define permitted viewers, required fields per event, payload bounds, and retention before exposing an audit API. Apply the [retention policy](../../inframeld-knowledge/references/deletion-and-retention.md) to attribution and surviving events too.

<a id="tables-integrated-with-later-features"></a>

## Tables integrated with later features

The following are integration points, **not records to create before their owning feature exists**. Each feature supplies its real resource, lifecycle, columns, and migration. Access still owns grants and permission policy. A cross-domain foreign key does not transfer ownership of the resource.

| Later table / relationship | Proposed key and references | Delivery boundary |
| --- | --- | --- |
| `pipeline_action_grants` | `(project_id, pipeline_id, recipient_principal_id, action)` PK. Scoped FK to real Pipeline and recipient project membership. The common grant fields/checks. | With the Pipeline feature. Build and its other settled actions use the fixed catalogue. |
| `deployment_action_grants` | `(project_id, deployment_id, recipient_principal_id, action)` PK. Scoped FK to real Deployment and recipient project membership. The common grant fields/checks. | With Deployments/Releases. Query, Manage releases, configuration, and Delete stay separate under [Bound administration, grants, and recovery](memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery). |
| Document/group allowlist join | `(project_id, document_id, group_id)` unique. Scoped FKs to real Document and access group. | Owned by Knowledge, with document-access checks following [Access policy](query-and-document-authorization.md#documents). The current nonempty allowlist belongs to the logical Document and protects all its versions. No per-version access copy. |
| Project upload-default/group join | `(project_id, group_id)` unique. Scoped FK to project/group, with the owning default configuration and revision. | Default provisioning/configuration under [From a new account to a first useful answer](../../inframeld-architecture/references/first-use-and-private-defaults.md) and its authorized update workflow. Applies to future admissions. Not an automatic change to existing Documents. |
| Active upload and source-configuration group references | Scoped FKs from their real configuration/intent records to each group they currently reference. | Owning Knowledge workflows. These references must block deletion of an in-use group. Historical snapshots need their separate retention treatment. Source configuration, credential administration and deletion are human-only under the [fixed Access catalogue](actions-and-initial-grants.md#capability-catalogue). Synchronization has its separately granted authority, as explained in [Knowledge](../../inframeld-knowledge/references/documents-and-collections.md). |

Invitation and admission, provisioning completion and retry state, idempotency reservations, and cleanup jobs belong to the workflows that need them. They follow the shared job contract. They are not missing permission tables or a reason to duplicate Kratos credentials and sessions.

<a id="implementation-boundary"></a>

## Implementation boundary

The initial migration creates the shared Access records and their core relational constraints. It does not deliver every administration workflow. Implemented Kratos/Hydra adapters handle the delivered human authentication paths. The accepted target assigns private defaults to onboarding and grants/handover/revisions to Access administration. Access owns document-readability policy, while Knowledge supplies authoritative Document/version lifecycle and audience observations. Those broader workflows remain unfinished where their references say so. The incoming-credential workflow handles application keys. Pipelines and Releases add their own resource tables and grants. These workflows build on the foundation, and describing them here does not mean they are implemented.

The implemented [PostgresDocumentAccessFactsReader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_document_access_facts_reader.py) reads existing Access tables for the [document-access foundation](query-and-document-authorization.md#document-access-foundation). Caller-owned READ COMMITTED coordination precedes refreshed actor, Project, membership, credential/recovery and audience-group facts. The reader reports which supplied groups exist in the exact Project, while the service and policy validate the complete original audience without pruning missing or foreign IDs. It creates no Document table, audience join or migration. Knowledge's future joins still supply trusted Document/version pairs, live states and one current logical Document audience for all versions. Receivers own refreshing those observations at every protected boundary and closing transactions before network work.

The migration stores nonempty action identifiers but does not yet restrict them to the code-owned action catalogue. Application policy must reject unsupported actions, and database checks can be added when stable action IDs are finalized. Status checks limit the values in the database, but application policy still decides which transitions are allowed. Index tuning and event-specific audit rules remain open engineering details.

PostgreSQL integration tests verify that all 14 tables are created and cover selected relational rules, including identity-link uniqueness, human-only assignments, required group-manager membership, cross-project references, and duplicate grants. Authorization tests cover current principal status, project membership, exact action grants, and hidden-versus-denied outcomes. These tests do not qualify administration, handover, or concurrent-write workflows. The separate document-access foundation has local unit and PostgreSQL qualification for current Access facts and policy. Real Knowledge joins, retrieval, model egress, history and complete product disclosure remain subject to each receiving feature's integration tests.

The [Access write protocol](grant-administration.md#storing-access-and-handling-simultaneous-changes) keeps current checks, any required expected revision, the change, revision increment, and audit event in one short transaction. Ordinary permission reads do not take exclusive administration locks. External calls stay outside these transactions. Code defines the supported actions and eligible human/application recipients.

<a id="implemented-persistence-authority"></a>

## Implemented persistence authority

For exact delivered columns, keys and indexes, read [0001_initial](../../../../apps/backend/migrations/versions/0001_initial.py), then [0002 reservations](../../../../apps/backend/migrations/versions/0002_idempotency_reservations.py), [0003 installation identity](../../../../apps/backend/migrations/versions/0003_installation_identity.py), [0004 recovery](../../../../apps/backend/migrations/versions/0004_identity_recovery.py) and [0005 credential versions](../../../../apps/backend/migrations/versions/0005_human_credential_versions.py). Logical and proposed physical relationships above do not override these migrations or establish future tables as delivered. Partial ORM mappings are adapter definitions.

<a id="project-metadata-persistence"></a>

## Approved Project metadata and repair persistence

**Not implemented at this recording checkpoint.** [ADR-0124](../../../../docs/adr/ADR-0124-authorize-project-metadata-changes-explicitly.md) and the [owning decision](decision-project-metadata-authority.md) require a distinct initially nullable Project selector and metadata revision. Preserve the existing unrestricted `projects.name` text exactly as the legacy Display name. Reads/replay and selector-only writes must not apply submitted-replacement validation to that retained value. Physical column/table names remain migration-owned choices.

Store current/retired exact name bindings with permanent resource identity, authoritative installation/Organization/kind/scope and binding revision. Enforce scoped collisions/non-reuse atomically, including inaccessible resources without disclosure. Metadata revision remains separate from `access_revision`. Save reservation, metadata, audit and original outcome together. Name retirement retains only the accepted minimal safety metadata under the [retention policy](../../inframeld-knowledge/references/decision-retention-erasure-policy.md).

`edit-project-metadata` is a human-only exact Project action. #120 must extend current eligibility and original-request authority recognition while preserving existing accepted actions and the fixed `create-access-groups` grant-route boundary. No automatic grant backfill follows from a migration.

The narrow host repair needs typed repair receipt data containing the original safe result and exact reviewed meaning, operator attribution/reason and before/after revisions. Preserve installation/operator-request-ID uniqueness across modes. Existing recovery receipts must be recognized before recovery-specific decoding. Preserve their real recovery/run fields and replay behavior, without fictitious recovery values for a metadata repair. Assignment, Access revision, required audit and receipt commit together. Keyed fingerprints exclude replaceable proof bytes, which never enter persisted receipts/audit. The [repair workflow](host-maintenance.md#project-metadata-authority-repair) owns proof, current-state checks and safe replay ordering.

<a id="stranded-authority-repair-persistence"></a>

## Retain an exact Access-owned repair original

[Migration 0030](../../../../apps/backend/migrations/versions/0030_stranded_authority_repair.py), following `0029_application_key_revocation`, adds `stranded_authority_repair_receipts` for group-manager and broader Access-owned action-grantor originals. Its [typed row](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/stranded_authority_repair_receipt_row.py) stores installation/request, Organization, recipient and expected Kratos identity IDs, keyed fingerprint, before/after revisions, responsibility/target kinds and the applicable exact target/action IDs. The checks enforce the closed Access target/action combinations, a 32-byte fingerprint and exactly one revision increment within the safe integer range.

The primary key is the common installation/operator-request identity. Its restrictive foreign key references `host_maintenance_receipts`. Mutable Project, group, account and assignment rows are not parents of this historical payload, so their later removal cannot erase or retarget the original. A retained receipt establishes historical meaning and result, not current authority.

[The writer](../../../../apps/backend/src/inframeld_backend/access/infrastructure/writers/postgres_stranded_authority_repair_writer.py) retains the existing `project_metadata_repair_receipts` payload for `edit-project-metadata`. [The fingerprint service](../../../../apps/backend/src/inframeld_backend/access/application/services/stranded_authority_fingerprint_service.py) preserves that subset's original canonical meaning. Both payloads share the cross-mode host operation namespace. Repair leaves recovery-operation, run and deadline fields absent rather than inventing recovery work.

Record the common receipt, exact payload, assignment, one Organization or Project revision increment and required audit in one caller-owned transaction. [The service](../../../../apps/backend/src/inframeld_backend/access/application/services/stranded_authority_repair_service.py) checks current proof-bound credential eligibility and applicable membership before consulting the original. Matching replay returns the original revision without regranting. Proof tokens are neither stored nor included in the stable fingerprint.

Migration 0030 is implemented and locally PostgreSQL-qualified in disposable databases. An existing installation still requires an explicit schema upgrade. Startup and the repair consumer do not migrate. Downgrade refuses retained broader repair originals or an unmatched common repair original, rather than deleting history or reversing assignments. The private installed-command path has separate local real-Ory qualification, while full operator qualification remains unfinished. [Host maintenance](host-maintenance.md#access-owned-authority-repair) owns the complete workflow and future receiver limits.
