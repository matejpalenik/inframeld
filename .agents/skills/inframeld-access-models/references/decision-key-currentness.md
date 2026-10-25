# PD-ACCESS-01: Check application-key currentness at the right boundary

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

SupportBot presents key K1. Verification succeeds, but Alice revokes K1 before the grant operation authorizes its work. Returning the earlier verified identity is insufficient: the protected operation must apply the selected current-key rule. A lost response creates the same question before returning a saved result.

Access already owns fresh key-state checks. What remains undefined is the exact verifier input/result interface, observation checkpoints and coordination between authorization, revocation and completion. Different callers could otherwise use different meanings of “current,” especially when expiry occurs during an operation.

## Accepted context and evidence

The selected verifier returns only ApplicationKeyId and associated PrincipalId. Its authentication service loads the current account and checks admission. Existing authorizers are the selected owners of key binding, expiry and revocation checks before protected incoming work or replay. These application-key checks are accepted target behavior, not an implemented verifier path. Invalid credentials return None, recognized verification availability failures raise DependencyUnavailableError, and unexpected failures/cancellation propagate. No credential fallback is permitted.

The full key format, verifier algorithm, lifetime and two-usable-key limit are already selected. The human OAuth generation flag being inapplicable does not validate an application key. The production application-key path remains unfinished.

## Alternatives and trade-offs

1. **Coordinate revocation and protected writes through the existing transaction.** Load current key facts with the operation’s authorization facts and coordinate conflicting revocation through a documented lock or conditional check. This gives a clear ordering point for database effects, but adds contention and requires a fixed lock order.
2. **Use versioned observations with explicit final checks.** Record the relevant observed key state and check it again at the agreed effect/disclosure boundary. This can reduce time holding locks, but every participating operation must honor the check. It cannot make a remote call atomic with PostgreSQL.

## Non-binding recommendation

**Proposal only.** Prefer extending the existing facts projections and transaction coordination rather than adding a credential-guard service. Select the exact expiry clock, ordering point and disclosure/dispatch checks using the first real consumer. The alternatives concern enforcement mechanics, not permission to weaken fresh verification.

## Decision trigger and stopping boundary

Before defining the application-key verifier/authenticator contracts or implementing key-aware authorizers and protected replay.

Pause only code that must choose these currentness semantics. Existing human grant behavior and qualification research can continue under their accepted contracts.

## Architectural impact and dependencies

Access verifier, authentication service, facts projections, authorizers and revocation workflow. Shared admission/replay callers and key request sequence diagrams must agree. No new public status code is implied.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](decision-admitted-work-authority.md). Only when the consumer admits or resumes durable background work.

## Open questions and required evidence

- Which authoritative clock and boundary determine expiry?
- How does revocation order against a concurrent authorized write or response?
- Which read/dispatch boundaries require a repeated observation?
- How are deadlocks, timeouts and uncertain commits handled without automatic retries?

## Sources and finalization

- [Accepted key format and lifetime](../../../../docs/development/access-control.md#application-key-contract).
- [Existing authorizers and remaining contracts](../../../../docs/development/access-control.md#application-key-current-authorization).
- [Minimal verifier split](../../../../docs/adr/ADR-0074-separate-application-key-verification-from-local-admission.md).
- [Evidence records](../../../../docs/development/data-model.md#authentication-evidence-records).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
