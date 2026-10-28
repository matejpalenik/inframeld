# ADR-0066: Use typed operation contexts and Command classification

**Status:** Accepted. Partially supersedes ADR-0065's idempotency input contract. Its application-owned transaction decision remains unchanged.

**Date:** 2026-10-20

## Context and Problem Statement

Alice grants Bob permission on Support. Her Command describes the requested grant, authentication identifies Alice, and current authorization establishes Support's organization and project. Repeating these fields manually at each idempotency call makes their sources harder to follow.

Project Commands should explicitly implement an interface requiring a project ID, with each concrete dataclass declaring its own fields. Organization-wide changes need no project. We also need the same field-based convention for authorization results without weakening required project IDs into optional fields.

## Considered Options

- Keep explicit scalar idempotency arguments. This is simple but repeats extraction from contexts at each call.
- Pass the business Command to idempotency. This couples retry scope to Command families instead of the scope established by authorization.
- Pass existing contexts and current authorized scope. This preserves the sources of identity and scope and centralizes reservation mapping.
- Use abstract properties or inherited data records for required fields. Properties conflict with ordinary dataclass field overrides under strict Pyright, while inherited data supplies fields rather than requiring concrete declarations.
- Use explicit field-based Protocols. Concrete records declare their own fields. A project-type parameter on authorization scope handles both required and absent projects.

## Decision Outcome

Keep `Command` as a nominal classification base without fields, dispatch or execution. Define the separate `ProjectCommand` Protocol with a required `project_id: ProjectId`. Concrete project Commands explicitly inherit both and declare their fields on standard frozen, slotted dataclasses. A Protocol cannot itself extend a nominal class. Commands remain business input and may validate local invariants without I/O.

Define `AuthorizedOperationScope[ProjectScope: ProjectId | None]` with required organization and project fields. Project action and grant authorization results explicitly implement `AuthorizedOperationScope[ProjectId]`. The grant result also carries its existing access revision. Organization scope can use an absent project. The type parameter preserves exact field types because ordinary Protocol fields are invariant.

Make `OperationIdempotency.find_or_reserve()` generic over that project type. Its required keyword-only inputs are `context`, `access`, `authorization`, `fingerprint` and `expected_replay_kind`. The caller authenticates first and authorizes current state before every lookup or replay. `IdempotencyService` alone maps the authenticated actor, authorized organization/project, retry metadata and fingerprint bytes into the unchanged reservation-writer request. It does not inspect a Command, infer scope or decide permissions.

The complete grant workflow checks that the returned project matches the Command immediately after authorization, before any reservation lookup or replay. A mismatch raises an internal runtime error and rolls back the transaction. Do not silently redirect the request or rewrite the Command. After a match, reservation, grant persistence and audit use organization/project scope from authorization. Requested recipient, action and expected revision remain on the Command, and actor identity remains on access. This check binds scope only. The authorizer still owns current permission and project/organization checks under the existing locks.

`RequestFingerprint` validates an immutable 32-byte digest and hides it from its representation. The existing HMAC algorithm, purpose, canonical bytes and stored digest remain unchanged. The four distinct workflow outcomes retain their existing meanings and failure behavior.

## Consequences

- The service call uses existing typed objects while keeping authorization, reservation and business changes visible in the workflow.
- Strict Pyright rejects wrong field types and instantiation of an explicit implementation missing a required field. It does not necessarily report the missing member at the class declaration. Annotations are not runtime input validation.
- Field Protocols do not express read-only access. Concrete Commands and DTOs remain frozen, and consumers must not mutate context through these interfaces.
- Nominal Command classification and these two required-field interfaces are narrow exceptions to the repository's normal preference for behavioral Protocols. They do not justify a generic record framework or more empty classification interfaces.
- Scope results describe checks performed in the current transaction. They are not authorization certificates or reusable permission snapshots.
- The complete grant workflow still owns its transaction. The admission helper retains its caller-owned transaction. No schema, HTTP, permission, lock, deadline or recovery-lifecycle change follows from these contracts.

## Links

- [ADR-0068: membership aggregate and repository](ADR-0068-model-project-grants-through-project-membership-aggregates.md) retains these input and scope contracts while moving assignment transitions into the domain model.
- [ADR-0065: application-owned write transactions](ADR-0065-application-services-own-write-transactions.md).
- [ADR-0067: typed authorization capabilities](ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) adds the common calling convention and qualifies both existing consumers without changing these operation-context contracts.
- [Command conventions and grant flow](../../.agents/skills/inframeld-python-standards/references/component-roles-and-imports.md#component-conventions).
- [Idempotency input sources](../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#reservation-inputs) and [temporary records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#principal-eligibility-inputs).
- [Access implementation evidence](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#shared-principal-eligibility).
- [Python Protocol specification](https://typing.python.org/en/latest/spec/protocol.html), including explicit implementations and generic field invariance.
