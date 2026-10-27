# ADR-0068: Model project grants through project membership aggregates

**Status:** Accepted. Implemented for the existing human use-only assignment workflow. Partially supersedes ADR-0065's grant-writer boundary, retaining application-owned transactions.

**Date:** 2026-10-22

## Context and Problem Statement

Alice grants Bob permission on Support. Bob may already hold several project action grants, including delegation rights. The operation must reject a duplicate without replacing or downgrading that assignment. Previously the application service passed assignment fields to a writer that inserted a row. That kept persistence atomic but left no domain model owning Bob's collection and assignment transition.

Loading the whole Project and every member would broaden the aggregate beyond this change. We need a focused domain owner while retaining current authorization, project-wide coordination, replay behavior and audit correlation.

## Considered Options

- Retain the field-based grant writer. It is a small persistence capability, but the assignment transition has no aggregate owner.
- Make Project own every membership and grant. This puts all project changes behind one object but requires loading unrelated members for a single-recipient change.
- Use a ProjectMembership aggregate for one member's complete direct project grants. This keeps cohesive assignment rules in the domain while project locks and revisions continue coordinating across members.

## Decision Outcome

Use `ProjectMembership`, identified by project and principal, with read-only organization/kind metadata and a private direct-grant collection. Its immutable `ProjectActionGrant` children use project, recipient and action identity. `ProjectGrantLevel` expresses use-only and use-and-grant without changing the persisted boolean. Reconstitution rejects duplicate actions, wrong-scope children and application delegation rights. Historical attribution may be absent. New use-only assignment records its actor and rejects any existing assignment without mutation.

Inject the specific `ProjectMembershipRepository` into `ProjectGrantChangeService`. Preserve the ordering: current authorization, requested-scope match, idempotency, replay branch, expected revision, membership load, loaded-target validation, domain assignment, save and completion. Replay returns before loading membership. The service translates the domain duplicate error into the existing conflict and supplies the checked authorization revision and original operation ID to save.

`PostgresProjectMembershipRepository` uses the same request-local session and requires an active caller-owned transaction. One scoped typed outer join loads existing membership and all direct grants. It never provisions a missing membership. Repeated loads return the same aggregate instance. Immutable infrastructure snapshots compare state values independently of identity equality. Instances and snapshots are bound to that repository and transaction and become unusable after a failed save or transaction end.

Unchanged saves write nothing. Supported additions conditionally increment the active project's revision once, insert without overwriting rows and append existing typed audit events through the injected audit writer. Preserve existing values, attribution and database timestamps. Advance snapshots only after all persistence and audit succeed. Reject unsupported changes and propagate errors/cancellation for the owner to roll back. The repository opens no transaction, takes no explicit locks, commits nothing and retries nothing.

## Consequences

- The service reads as load, domain behavior and save, while authorization and operational safeguards remain explicit application steps.
- The composite identities reflect existing records. No new grant ID, membership revision, table or migration is needed.
- A membership's complete direct collection must be loaded. Snapshot and transaction-lifetime handling add infrastructure code and require focused persistence tests.
- Existing project locks and project-wide revisions coordinate different membership aggregates. The repository neither replaces authorization nor weakens database uniqueness/foreign keys.
- Discard loaded aggregates and repositories after commit, rollback or failed save. Do not catch a persistence error and continue to commit partial work.
- Only the existing human use-only assignment workflow is implemented. Membership creation/removal, grant updates/revocation and cross-member lifecycle operations remain deferred. No generic repository framework is introduced.

## Links

- [ADR-0065: application-owned write transactions](ADR-0065-application-services-own-write-transactions.md), [ADR-0066: trusted scope inputs](ADR-0066-use-typed-operation-contexts-and-command-classification.md) and [ADR-0067: authorization capabilities](ADR-0067-standardize-authorization-capabilities-with-typed-requests.md).
- [Implemented request chain](../../.agents/skills/inframeld-coding-standards/references/services-and-use-cases.md#grant-command-flow) and [repository responsibilities](../../.agents/skills/inframeld-coding-standards/references/aggregates-and-repositories.md#membership-aggregate-and-repository).
- [Access behavior and verification](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#project-membership-grant-model), [domain/storage mapping](../../.agents/skills/inframeld-access-models/references/implemented-access-models.md#project-membership-aggregate) and [retry ordering](../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#reservation-inputs).
- [Domain model](../../apps/backend/src/inframeld_backend/access/domain/entities/project_membership.py), [repository](../../apps/backend/src/inframeld_backend/access/infrastructure/repositories/postgres_project_membership_repository.py), [repository integration scenarios](../../apps/backend/tests/integration/access/test_project_membership_repository_postgres.py), [grant scenarios](../../apps/backend/tests/integration/access/test_project_grant_change_postgres.py) and [recovery/failure scenarios](../../apps/backend/tests/integration/access/test_recovery_authorization_postgres.py). Fresh validation results belong to the Access guide.
