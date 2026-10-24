# Transactions, durable jobs and safe retries

Alice grants Bob a permission and loses the response. The server may already have committed it. A retry must find the original outcome under current authority rather than granting again or returning an old answer to a now-ineligible caller.

## Operation identity and current authority

Idempotency recognizes the same caller, key and request meaning as one operation. The same key with different meaning conflicts. Expected revisions separately detect competing changes. A stored outcome is metadata, not permission. Authenticate and authorize before reservation or replay.

The admission context, authenticated `access`, current `authorization`, typed `RequestFingerprint` and expected replay kind are explicit inputs to `OperationIdempotency`. Actor identity comes from access. Organization/project scope comes from authorization, never from inspecting the Command. Generic idempotency preserves the authorization result's project type. `IdempotencyService` alone assembles the low-level reservation request.

## Follow the implemented grant pattern

1. The static `ProjectUseOnlyGrantMapper` creates a flat Command from HTTP input. It constructs the typed response directly after narrowing the supported action. Fingerprint meaning belongs to the service.
2. The service computes the unchanged fingerprint before opening `TransactionManager`. Bootstrap supplies its adapters one clean request-local session and closes it afterward.
3. Inside the transaction, call `ProjectGrantAuthorizer` through the service's direct dependency. Immediately compare returned project scope to the Command, before reservation or replay. A mismatch raises an internal runtime error and rolls back. Scope matching does not replace current permission checks.
4. Pass current context/access/authorization/fingerprint/replay kind to idempotency. A completed retry can resolve its original outcome. New work retains the existing expected-project-revision check and lock/deadline contract.
5. Load the recipient through `ProjectMembershipRepository` in authorization scope. Check organization, project and recipient. Invoke `assign_use_only_grant()` with business details from the unchanged Command.
6. Save supported additions with the checked project-wide revision and original operation ID. Required audit, durable change and safe completion/replay metadata commit together.

Load/save stay outside narrow domain-error catches. Translate recognized aggregate rejections with stable application-owned messages and preserve causes. Persistence, audit, commit failure or cancellation must leave rollback with the service transaction. The repository neither commits nor retries and must discard transaction-bound instances after failure/end.

The Access-owned `ProjectOperationAdmissionService` and its request DTO also coordinate authorization and check returned project scope before lookup. They share `OperationIdempotency` while retaining their caller-owned transaction and rollback. Lower-level reservation adapters retain their existing contracts. Generic outcomes, reservation persistence and retries stay shared. Do not turn one complete product command into a claim that another workflow is qualified.

## Outcomes and background attempts

`IdempotencyService` validates low-level reservation projections and returns distinct new-work, completed synchronous, accepted asynchronous or recovery-required outcomes. Synchronous expiry is required. Asynchronous expiry remains optional. Preserve the expected replay kind and typed project/organization scope.

Durable jobs save accepted work and progress across client disconnects or worker restart. Admit work and its reservation atomically in a short transaction, then perform external work outside it. Only the current fenced attempt may publish. A fence is an attempt/revision check preventing stale publication, not a way to cancel remote work.

A paid model timeout may mean the request ran and was billed. Missing output, a nonzero exit or unconfirmed cancellation cannot authorize a new dispatch. Frozen vector storage retries have a separate bounded protocol using already captured bytes. Identity-recovery cleanup has its own trusted original-obligation and bulk-provider boundaries, not another generic state machine.

## Recovery boundaries

Same-key replay resolves original inputs and target before new current settings. For a default alias, find the original logical-route record before resolving a rebound target, preventing another paid query. Stale reviewed revisions conflict. Preserve original installation/account/project identity through job recovery and imports.

Generated credentials are shown once. Keep secret-bearing fingerprints keyed and replay metadata secret-safe. Submitted provider secrets are never echoed. Completed answer retries are receipt-only rather than saved full-answer replay or regeneration. Required authorization, audit and accounting cannot be weakened by diagnostics failure.

Disaster restore can restore old permissions and retry history. Follow coherent security reconciliation before serving/replay rather than assuming historical state is current authority. Retention bounds remain explicit, not an unlimited content archive.

## Status and sources

The grant chain is the implemented reference. Job workflows, later commands, recovery production wiring and exact CLI outcomes retain their own qualification. Do not add a universal executor, command bus, generic repository or speculative recovery aggregate.

- [Grant chain](../../../../docs/development/application-structure.md#grant-command-flow), [service guide](../../../../docs/development/application-structure.md#service-writing-guide), [membership repository](../../../../docs/development/application-structure.md#membership-aggregate-and-repository), [jobs/idempotency](../../../../docs/development/jobs-and-idempotency.md) and [supporting records](../../../../docs/development/data-model.md#shared-supporting-records).
- [ADR-0065](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md), [ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md), [ADR-0067](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md), [ADR-0068](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md) and [error mapping](../../../../docs/development/error-handling.md#stable-domain-error-mapping).
