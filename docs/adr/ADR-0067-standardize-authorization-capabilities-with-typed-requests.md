# ADR-0067: Standardize authorization capabilities with typed requests

**Status:** Accepted. Supplements ADR-0064, ADR-0065 and ADR-0066 without changing their permission, transaction or scope decisions.

**Date:** 2026-10-22

## Context and Problem Statement

Alice wants to perform a project action. Separately, she wants to grant Bob permission to perform it. These decisions share current principal eligibility, but the second requires delegation authority and checks on Bob. A common calling convention should make both easy to invoke without hiding their different rules.

The complete grant workflow and the admission helper already use specific authorization capabilities. They need consistent typed inputs and scope matching before reservation or replay. The grant service owns its transaction, while the helper remains caller-transaction bound.

## Considered Options

- Keep unrelated method signatures. This preserves explicit operation names, but each caller must learn another input convention.
- Add a universal authorization service, registry or policy language. This centralizes dispatch but introduces machinery and optional inputs beyond the current workflows.
- Standardize a thin generic Protocol and retain specific permission families. This gives callers a predictable method while keeping policy decisions and data loading explicit.

## Decision Outcome

Use Access-owned `Authorizer[RequestType, ResultType]` with the required keyword-only method `require_authorization(access, request)`. Its method is abstract. Specific family Protocols explicitly specialize it, and concrete services and test doubles explicitly inherit their family and mark implementations with `@override`. An inherited required method is a behavioral contract, not an empty marker Protocol.

`ActionAuthorizer` accepts `ProjectActionAuthorizationRequestDTO`, containing the project and required action, and returns `ProjectActionAuthorizationDTO`. Trusted application workflows select the action required for their operation. An HTTP caller cannot choose a weaker action to protect that operation.

`ProjectGrantAuthorizer` accepts `ProjectUseOnlyGrantAuthorizationRequestDTO`, containing project, recipient and the action being delegated, and returns `ProjectGrantAuthorizationDTO`. The result retains the current project access revision. Use authority and delegation authority remain distinct.

Authorization requests are standard frozen, slotted application DTOs. They do not inherit business Commands or contain expected revisions, retry context or fingerprints. Their annotations add no runtime validation. Current existence, eligibility, permissions and visibility are checked through the existing readers and policies. Reader contracts remain unchanged.

Both consumers compare returned project scope with the requested project before idempotency lookup, including replay. A mismatch raises an internal runtime error. After matching, use the returned authorization scope downstream, preserve the business input unchanged and retain actor identity on access. The grant service rolls back its transaction on failure. The admission helper leaves transaction ownership and rollback with its caller.

## Consequences

- New ordinary actions reuse the existing family. Add a request, Protocol and implementation when a decision needs materially different inputs or rules, rather than for every endpoint.
- The generic Protocol standardizes signatures. It does not execute shared policy, force a workflow to call authorization, or make results portable permission certificates. Shared eligibility remains in its domain policy. Behavioral tests establish ordering and denial before disclosure or mutation.
- Preserve visibility and recipient-disclosure ordering, current authorization on replay, recovery coordination and existing database deadlines. Authorizers do not open transactions, commit or mutate business state.
- Qualify the convention through the complete grant workflow and the existing admission helper. The helper is not a second complete product write workflow. Account UI, CLI lifecycle and provider-cleanup qualification remain separate work.
- This convention introduces no authorization dispatcher, registry, policy engine, generic write executor or grant-writer refactor. The old authorization method names are removed after callers migrate, without compatibility wrappers.

## Links

- [Typed authorization capabilities](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#typed-authorization) and [grant request chain](../../.agents/skills/inframeld-coding-standards/references/services-and-use-cases.md#grant-command-flow).
- [Current Access behavior and evidence](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#shared-principal-eligibility).
- [Authorization and idempotency ordering](../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#reservation-inputs) and [temporary records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#principal-eligibility-inputs).
- [ADR-0064: shared eligibility and focused boundaries](ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md), [ADR-0065: transaction ownership](ADR-0065-application-services-own-write-transactions.md) and [ADR-0066: typed operation contexts](ADR-0066-use-typed-operation-contexts-and-command-classification.md).
