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
- Organizations and projects have a nonnegative integer `access_revision`. Advance the relevant scope's revision for each committed Access administration change. Administration requests carry the expected revision so stale changes are rejected, including removal followed by regrant. It is not a cached permission snapshot. A project change does not advance every other project's revision. The administration contract owns its request/response representation.

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
| `application_credentials` | Stable credential ID. `(project_id, application_principal_id)` FK to application account. Stored verifier and safe metadata, expiry/revocation, audience and the required binding. | Owned by the incoming-credential workflow. No per-key permission rows. Enforce the two-usable-key limit transactionally. The [accepted key contract](application-key-contracts.md) fixes format, verifier algorithm and lifetimes. The [accepted currentness contract](application-key-contracts.md#verification-results-and-unresolved-currentness) selects checkpoints and ordering. Remaining physical binding columns are implementation work. |
| Document/group allowlist join | `(project_id, document_id, group_id)` unique. Scoped FKs to real Document and access group. | Owned by Knowledge, with document-access checks following [Access policy](query-and-document-authorization.md#documents). The current nonempty allowlist belongs to the logical Document and protects all its versions. No per-version access copy. |
| Project upload-default/group join | `(project_id, group_id)` unique. Scoped FK to project/group, with the owning default configuration and revision. | Default provisioning/configuration under [From a new account to a first useful answer](../../inframeld-architecture/references/first-use-and-private-defaults.md) and its authorized update workflow. Applies to future admissions. Not an automatic change to existing Documents. |
| Active upload and source-configuration group references | Scoped FKs from their real configuration/intent records to each group they currently reference. | Owning Knowledge workflows. These references must block deletion of an in-use group. Historical snapshots need their separate retention treatment. Source configuration, credential administration and deletion are human-only under the [fixed Access catalogue](actions-and-initial-grants.md#capability-catalogue). Synchronization has its separately granted authority, as explained in [Knowledge](../../inframeld-knowledge/references/documents-and-collections.md). |

Invitation and admission, provisioning completion and retry state, idempotency reservations, and cleanup jobs belong to the workflows that need them. They follow the shared job contract. They are not missing permission tables or a reason to duplicate Kratos credentials and sessions.

<a id="implementation-boundary"></a>

## Implementation boundary

The initial migration creates the shared Access records and their core relational constraints. It does not deliver every administration workflow. Implemented Kratos/Hydra adapters handle the delivered human authentication paths. The accepted target assigns private defaults to onboarding, grants/handover/revisions to Access administration and permitted source-content checks to Knowledge. Those broader workflows remain unfinished where their references say so. The incoming-credential workflow handles application keys. Pipelines and Releases add their own resource tables and grants. These workflows build on the foundation, and describing them here does not mean they are implemented.

The migration stores nonempty action identifiers but does not yet restrict them to the code-owned action catalogue. Application policy must reject unsupported actions, and database checks can be added when stable action IDs are finalized. Status checks limit the values in the database, but application policy still decides which transitions are allowed. Index tuning and event-specific audit rules remain open engineering details.

PostgreSQL integration tests verify that all 14 tables are created and cover selected relational rules, including identity-link uniqueness, human-only assignments, required group-manager membership, cross-project references, and duplicate grants. Authorization tests cover current principal status, project membership, exact action grants, and hidden-versus-denied outcomes. These tests do not qualify administration, handover, or concurrent-write workflows. Document-evidence filtering is also separate and must be verified with its owning feature.

The [Access write protocol](grant-administration.md#storing-access-and-handling-simultaneous-changes) keeps current checks, any required expected revision, the change, revision increment, and audit event in one short transaction. Ordinary permission reads do not take exclusive administration locks. External calls stay outside these transactions. Code defines the supported actions and eligible human/application recipients.

<a id="implemented-persistence-authority"></a>

## Implemented persistence authority

For exact delivered columns, keys and indexes, read [0001_initial](../../../../apps/backend/migrations/versions/0001_initial.py), then [0002 reservations](../../../../apps/backend/migrations/versions/0002_idempotency_reservations.py), [0003 installation identity](../../../../apps/backend/migrations/versions/0003_installation_identity.py), [0004 recovery](../../../../apps/backend/migrations/versions/0004_identity_recovery.py) and [0005 credential versions](../../../../apps/backend/migrations/versions/0005_human_credential_versions.py). Logical and proposed physical relationships above do not override these migrations or establish future tables as delivered. Partial ORM mappings are adapter definitions.
