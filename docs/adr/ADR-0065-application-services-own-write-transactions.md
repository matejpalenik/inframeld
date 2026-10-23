# ADR-0065: Application services own write transactions

**Status:** Accepted. Implemented for the project use-only grant command. Partially supersedes ADR-0064's placement of that transaction boundary. ADR-0066 partially supersedes the idempotency input contract below, while retaining transaction ownership. ADR-0068 partially supersedes the grant-writer boundary with a membership aggregate and specific repository, retaining this transaction decision.

**Date:** 2026-10-19

## Context and Problem Statement

Alice grants Bob permission and retries after losing the response. Current authorization, the operation reservation, grant, revision and audit must remain one atomic workflow. Previously the HTTP route opened the transaction and constructed the adapters, while the service interpreted replay state itself. That made the complete operation harder to reuse outside HTTP.

The accepted shared eligibility and Access lock rules remain in force. We need named operational collaborators that keep the service readable without moving permissions into the controller or collecting every dependency inside a transaction object.

## Considered Options

- Retain transaction ownership and concrete assembly in HTTP. This keeps the current arrangement but leaves another entry point responsible for reproducing its boundaries.
- Let the application service define the transaction through injected capabilities, with bootstrap supplying the request-local session. This makes the operation's complete behavior reusable and keeps its dependencies explicit.
- Put repositories, authorization and retry execution behind a generic work object or command framework. This centralizes plumbing but hides dependencies and adds machinery beyond the current workflow.

## Decision Outcome

Use the application-owned transaction and direct dependencies. The original implementation of `ProjectGrantChangeService` exposed `ProjectGrantChanger` and received `TransactionManager`, `ProjectGrantAuthorizer`, `OperationIdempotency`, `ProjectGrantChangeWriter` and its fingerprint service.

Static HTTP mapper methods convert validated input into a flat `AssignProjectUseOnlyGrantCommand` and construct the published response. The response mapper checks the supported action and calls the typed response constructor directly. Separate admission context carries the idempotency key and canonical method/route. The service computes the existing keyed fingerprint from the Command before starting database work.

Bootstrap opens a clean request-local session and constructs all database collaborators with it. `SqlAlchemyTransactionManager.begin()` rejects an already active transaction, commits normal completion and rolls back failures. It never silently joins a transaction, creates a savepoint or retries automatically. Commit errors propagate. Provider verification occurs before this transaction.

Inside the transaction, check current authorization before finding or reserving work. Return an authorized completed replay without another write. For new work, check the expected revision, save the audited grant and record safe replay metadata. `IdempotencyService` validates the storage result and required synchronous expiry before producing a workflow outcome. The grant service returns `CompletedSynchronousOperationDTO` and rejects recovery-required or unexpected asynchronous outcomes before commit. The reservation adapter retains scope uniqueness, fingerprint comparison and expiry behavior. In the original implementation, audit persistence was part of the grant writer's atomic contract, through an injected typed `AuditEventWriter`. [ADR-0068](ADR-0068-model-project-grants-through-project-membership-aggregates.md) replaces that collaborator with `ProjectMembershipRepository`. For new work the service now loads and checks the recipient's membership, invokes its domain assignment and saves supported additions. Repository persistence retains the project-wide revision and required audit on the same session. Neither it nor the audit writer commits. The service's authorization, replay and completion ordering remains unchanged.

The implemented retry boundary uses four distinct application records for new reservations, synchronous completion, asynchronous acceptance and required recovery. The low-level `OperationReservationResultDTO` stays at the reservation boundary. Outcomes describe metadata, not authorization. `ProjectOperationAdmissionService` also delegates retry decisions to `OperationIdempotency`, after current authorization and scope derivation, while retaining its caller-owned transaction. This shares retry behavior without claiming a second complete product workflow.

The initial shared API received the admission context, explicit principal/organization/project IDs, fingerprint bytes and expected replay kind. [ADR-0066](ADR-0066-use-typed-operation-contexts-and-command-classification.md) replaces these scalar inputs with the existing access context, current authorized scope and typed fingerprint alongside the admission context and replay kind. The implemented service maps them to the same low-level reservation request, preserving all values. The grant workflow passes its context directly, while the admission helper adapts its existing request. Command classification and required-field contracts do not change transaction ownership or move authenticated identity onto Commands.

## Consequences

- HTTP stays responsible for authentication input, mapping and serialization. The complete database operation can be invoked through its application Protocol.
- Internal callers and tests supply a clean session instead of wrapping the public grant operation in another transaction. Concurrency tests pause real collaborators inside the operation to observe its locks.
- Ordinary adapter and admission-only helpers remain caller-transaction bound. This decision does not migrate every operation or change the persistence schema, permission rules, wire contract or recovery lifecycle.
- Context managers manage resource lifetime. The replay branch remains explicit, and safe result reconstruction stays with the owning operation and its HTTP mapper.
- New complete database writes should follow this example. No generic repository, command bus, workflow engine or large User aggregate is introduced.

## Links

- [Implemented request chain and component responsibilities](../development/application-structure.md#grant-command-flow).
- [Current Access checks](../development/access-control.md#shared-principal-eligibility), [idempotency](../development/jobs-and-idempotency.md#requests) and [attempt-local records](../development/data-model.md#principal-eligibility-inputs).
- [ADR-0064](ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md) retains shared eligibility and focused aggregate boundaries. [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md) retains write coordination.
- [SQLAlchemy transaction contexts](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#managing-transactions).
- [Grant integration scenarios](../../apps/backend/tests/integration/access/test_project_grant_change_postgres.py), [recovery and failure scenarios](../../apps/backend/tests/integration/access/test_recovery_authorization_postgres.py) and [transaction behavior](../../apps/backend/tests/integration/postgres/test_transaction_manager_postgres.py). Current validation results belong to the topic guides.
