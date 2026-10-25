# Implemented Access models and runtime identities

Alice loses a permission while the same local principal still identifies her. Bob's membership owns his direct project grants, but loading it does not authorize Alice to change them. These examples distinguish an object's identity, its observed state and its allowed business transitions.

**Status:** the linked Python definitions implement the models described here. Their existence does not establish all account, membership or credential workflows. Code owns exact declarations. No new application type, stored field or lifecycle operation is introduced by this reference.

Read only the relevant model below. For logical relationships use [Identity and grants](identity-and-grant-records.md). For database structure use [Access persistence](access-persistence.md). For complete implementation examples use [Coding Standards](../../inframeld-coding-standards/references/aggregates-and-repositories.md).

<a id="implemented-principal-model"></a>

<a id="implemented-principal-and-typed-values"></a>

## Implemented Principal and typed values

[`access/domain/entities/principal.py`](../../../../apps/backend/src/inframeld_backend/access/domain/entities/principal.py) defines the current immutable domain entity:

| Field | Application type | Meaning |
| --- | --- | --- |
| `id` | `PrincipalId` | Stable identity of the local actor. |
| `organization_id` | `OrganizationId` | Organization owning that actor. |
| `kind` | `PrincipalKind` | `HUMAN` or `APPLICATION`, stored as the existing lowercase strings. |
| `status` | `PrincipalStatus` | `ACTIVE`, `SUSPENDED`, or `RETIRED`, stored as the existing lowercase strings. |

Equality and hashing follow `PrincipalId`, so snapshots of one account remain the same entity after a status change. Authentication uses the state together to require an active human. This model adds no lifecycle command or speculative aggregate. Display names, audit attribution, memberships, and grants retain their separate existing records.

`PrincipalId`, `OrganizationId`, `ProjectId`, and `AccessGroupId` are distinct frozen, slotted objects wrapping a parsed UUID. They preserve all existing UUID values, while preventing accidental interchange in application contracts. ORM mappings keep UUID columns and adapters explicitly convert values. Existing migrations remain authoritative for their stored representation.

`IdentityAuthority` and `IdentitySubject` remain validated exact strings carried together in `VerifiedHumanIdentityDTO`. The identity reader returns current principal state without applying admission in SQL.

`AccessContextDTO` carries the authenticated `PrincipalId` and exactly one complete, non-secret [authentication evidence record](credential-and-recovery-records.md#authentication-evidence-records) for a browser session, human CLI OAuth credential or application key, as required by [ADR-0073](../../../../docs/adr/ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md). It retains no credential secret, mutable account status or permission snapshot. Current account and grant checks still run when authorizing an operation.

The implemented project target is `ProjectActionTargetDTO(ProjectId)`. No generic bare-UUID resource target is implied.

For component responsibilities and conversion examples, use [application conventions](../../inframeld-coding-standards/references/component-roles-and-imports.md#component-conventions). For HTTP outcomes and verification scope, use [the implemented authentication boundary](credential-dispatch.md#implemented-human-authentication).

<a id="project-membership-aggregate"></a>

<a id="implemented-project-membership-aggregate"></a>

## Implemented project membership aggregate

`ProjectMembership` is an in-memory Access aggregate with identity `(project_id, principal_id)`. It holds read-only organization/principal-kind metadata and the complete collection of that member's direct project grants. It adds no table or synthetic membership ID. Group membership, group-derived grants and cross-member lifecycle behavior are outside this collection.

Each immutable `ProjectActionGrant` child is identified by project, recipient and action. `ProjectGrantLevel` expresses `USE_ONLY` or `USE_AND_GRANT` in the domain. Infrastructure converts these to/from the existing `project_action_grants.can_grant` boolean. Nullable historical attribution remains valid, while new use-only assignments require an assigning principal. Duplicate assignment at either level is rejected without replacing the old grant. Applications cannot hold delegation rights.

The specific repository reconstitutes this model from `project_memberships` and all matching direct `project_action_grants` rows with one scoped typed outer join. Its private infrastructure snapshots compare complete values independently of entity identity. Loaded instances and snapshots belong to one active transaction, are never cached across requests, and must be discarded after a failed save or transaction end.

The supported delta is attributed use-only additions. An unchanged save does no writes. Additions preserve existing grant values, attribution and database-generated timestamps, conditionally increment the existing project-wide access revision once, and append required audit with the original operation ID. No membership version, new grant ID or schema migration is introduced. Authorization readers retain current eligibility/delegation checks and existing locks. [ADR-0068](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md) owns the aggregate decision, and [application structure](../../inframeld-coding-standards/references/aggregates-and-repositories.md#membership-aggregate-and-repository) owns transaction/snapshot behavior. Membership provisioning, updates/revocation and cross-member lifecycle operations remain deferred.

## Failures and implementation limits

An ID wrapper proves neither existence nor authority. `ProjectMembership` rejects duplicate assignments without replacing state, while persistence or audit failures propagate to the owning transaction. Its supported repository delta remains attributed use-only additions. Use the [complete service example](../../inframeld-coding-standards/references/services-and-use-cases.md) for authorization, replay, revision checking and commit ordering. Creating or removing memberships needs its separately approved workflow.

## Sources

[Principal](../../../../apps/backend/src/inframeld_backend/access/domain/entities/principal.py), [ProjectMembership](../../../../apps/backend/src/inframeld_backend/access/domain/entities/project_membership.py) and the [specific repository contract](../../../../apps/backend/src/inframeld_backend/access/application/protocols/project_membership_repository.py) own exact declarations. [ADR-0068](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md) records the aggregate boundary. [ADR-0073](../../../../docs/adr/ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md) records authentication evidence. Exact schema remains migration-owned.
