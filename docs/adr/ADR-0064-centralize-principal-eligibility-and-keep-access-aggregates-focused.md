# ADR-0064: Centralize principal eligibility and keep Access aggregates focused

**Status:** Accepted. Grant transaction placement is partially superseded by [ADR-0065](ADR-0065-application-services-own-write-transactions.md). Shared eligibility, linked-recovery/write coordination and the recovery checklist aggregate/repository are implemented. Later [provider cleanup and proof-backed release](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#implemented-execution-and-proof-backed-completion) implement the separate orchestration under the owning recovery contract and its qualification limits.

**Date:** 2026-10-18

## Context and Problem Statement

Alice can have a valid session and an existing grant while verified recovery cleanup temporarily blocks her product access. Authentication, action authorization and grant delegation must all respect that block. Passing a separate recovery boolean through each operation's records and method arguments spreads one account rule across several implementations.

Access already owns authorization, and PostgreSQL owns current relationships under ADR-0013. ADR-0002 permits purpose-built read projections, while ADR-0022 defines coordination between account and project changes. ADR-0058 keeps recovery blocks separate from suspension. The missing boundary is shared principal eligibility, not another permission engine or a replacement identity model.

Recovery may be admitted for a verified provider identity before it has a local principal. A principal therefore cannot own every recovery obligation. Project grants and memberships also have their own scope and lifecycle.

## Considered Options

- Refactor shared eligibility and authorization boundaries. Give common account rules one domain owner, carry their current inputs together, and retain operation-specific permission policies and read projections.
- Redesign Access around richer aggregates immediately. Small aggregates could protect account and recovery transitions, but authorization would still combine current facts across their boundaries. A broad redesign would not remove that requirement.
- Keep propagating separate eligibility fields through existing operation records. This minimizes the immediate refactor but repeats the same change across future operations.

## Decision Outcome

Choose the shared eligibility refactor, with focused aggregates introduced alongside the lifecycle behavior they protect.

### One common product-eligibility decision

Use one pure domain policy for current principal eligibility. Authentication, action and delegation policies compose it, then apply their own caller-kind, membership, target and authority requirements. Credential verification remains a separate responsibility.

The selected first implementation uses `PrincipalAccessPolicyInput` to carry the observed `Principal` and whether an unreleased recovery obligation blocks it. `PrincipalAccessPolicy` owns the active-account and no-pending-recovery decision. Both components are now implemented in human authentication, project action authorization and the supported human grant command.

Operation DTOs and policy inputs carry that cohesive input instead of copying its fields into every operation signature. These are values for one attempt, not an aggregate, a persisted eligibility flag or a reusable authorization certificate. At this decision’s initial boundary, `AccessContextDTO` contained only principal identity. [ADR-0073](ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md) later refines that context to require actor identity plus complete non-secret authentication evidence. The context still carries no cached account state or permission snapshot. This refinement does not replace the shared eligibility decision above.

### Stable authorization operations and explicit persistence

Application workflows invoke Access authorization operations. Access services coordinate current reads and error ordering, while domain policies own the decisions. Grant mutation orchestration delegates its visibility and delegation checks to a grant-authorization operation before reserving new work or returning a saved result.

Read adapters may collect principal state, recovery, membership and exact-grant facts in one typed projection. Prefer one coherent facts query when those values decide the same attempt. Sharing SQL expression construction is allowed, but a facts reader must not instantiate another executing reader merely to fill one field. This is a responsibility rule, not a ban on multiple statements in a transaction.

At adoption, the caller assembling the grant operation retained transaction ownership. [ADR-0065](ADR-0065-application-services-own-write-transactions.md) moves this boundary into the grant application service. The adapters remain caller-transaction bound. Grant changes acquire the shared organization lock and exclusive project lock before checking current facts and saving changes. Recovery for an already linked human acquires the conflicting exclusive organization lock. Keep bounded waits, and roll back failures. Never hold these transactions across identity-provider calls.

Preserve the visibility-before-authority distinction, including 404 for hidden projects and 403 for visible projects denied by recovery or missing authority. Missing installation metadata or unavailable dependencies cannot become an absent block. Replays require current authorization. Authentication deadlines, cookie protection, application eligibility and exact-target grants remain unchanged.

### Rich behavior at actual lifecycle boundaries

Introduce a focused recovery aggregate when implementing cleanup confirmation and release in #117. It protects the original recovery binding, provider outcomes and valid transitions. Release must also depend on authoritative current eligibility and other-pending-obligation facts, coordinated through persistence. Provider calls remain application orchestration outside the transaction.

The implemented `IdentityRecovery` keeps the original installation/provider/flow and subject, independent provider outcomes and release state. Its specific repository preserves the original operation ID, event kind and admission time as infrastructure metadata. Transaction-bound value snapshots and conditional updates prevent overwriting changed stored progress. These are implementation details within this decision, with no new schema. The future application workflow must check current eligibility and competing obligations under coordination locks before invoking release. The aggregate's local both-providers-confirmed guard and repository persistence do not complete that workflow. See [recovery records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records).

Add account lifecycle behavior to `Principal` with the suspension/restoration workflows that need it. Do not move all grants, memberships or provider recovery obligations into a large User aggregate. A domain transition method complements database constraints and locks rather than replacing them.

## Consequences

- A new common eligibility condition changes its shared input, policy, loading and tests instead of requiring another argument at every operation call site. New persistence facts still need real mapping and qualification.
- Application DTOs, dedicated policy inputs, explicit protocols and pure named policies remain useful. This choice does not introduce a generic authorization language, repository framework, command bus or request-wide permission cache.
- Ordinary authorization can use efficient projections. State-changing workflows gain aggregate behavior where it protects actual invariants.
- The refactor must preserve existing behavior and the developer's uncommitted recovery work. Passing policy tests alone does not qualify current-state reads, replay or concurrent writes.
- This decision refines the implementation boundaries of ADR-0002, ADR-0013, ADR-0022 and ADR-0058. It does not supersede their product, persistence or recovery rules.

## Links

- [Shared principal eligibility and authorization behavior](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#shared-principal-eligibility).
- [Component responsibilities and staged refactor](../../.agents/skills/inframeld-access-models/references/architecture.md#shared-access-eligibility).
- [Attempt-local inputs](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#principal-eligibility-inputs) and [recovery records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records).
- [Lightweight CQRS](ADR-0002-separate-commands-and-queries-without-a-command-bus-framework.md), [Access ownership](ADR-0013-keep-authorization-in-access-and-postgresql.md), [write coordination](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md) and [recovery blocks](ADR-0058-block-product-access-during-identity-recovery-cleanup.md).
- [PostgreSQL recovery authorization tests](../../apps/backend/tests/integration/access/test_recovery_authorization_postgres.py) check current-state replay, both linked-recovery/grant ordering cases and timeout rollback. [Recovery domain tests](../../apps/backend/tests/unit/access/domain/entities/test_identity_recovery.py) and [repository tests](../../apps/backend/tests/integration/access/test_identity_recovery_repository_postgres.py) cover checklist transitions and persistence. Provider cleanup, safe release orchestration and concurrent first-local-admission qualification remain [#117](https://github.com/matejpalenik/inframeld/issues/117) work.
