# PD-ACCESS-01: Check application-key currentness at the right boundary

**Status:** ACCEPTED on 2026-10-29 in [ADR-0100](../../../../docs/adr/ADR-0100-order-key-revocation-at-protected-boundaries.md). Implementation and qualification remain pending.

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract.

The developer explicitly approved all three permissions-and-jobs proposals on 2026-10-29 and requested repository and GitHub documentation. Acceptance selects the policy, not implemented behavior or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

SupportBot presents key K1. Verification succeeds, but Alice revokes K1 before the grant operation authorizes its work. Returning the earlier verified identity is insufficient: the protected operation must apply the selected current-key rule. A lost response creates the same question before returning a saved result.

Access already owns fresh key-state checks. The original analysis identified the verifier input/result interface, observation checkpoints and coordination between authorization, revocation and completion as unfinished. Different callers could otherwise use different meanings of “current,” especially when expiry occurs during an operation.

## Accepted context and evidence

The selected verifier returns only ApplicationKeyId and associated PrincipalId. Its authentication service loads the current account and checks admission. Existing authorizers are the selected owners of key binding, expiry and revocation checks before protected incoming work or replay. These application-key checks are accepted target behavior, not an implemented verifier path. Invalid credentials return None, recognized verification availability failures raise DependencyUnavailableError, and unexpected failures/cancellation propagate. No credential fallback is permitted.

The full key format, verifier algorithm, lifetime and two-usable-key limit are already selected. The human OAuth generation flag being inapplicable does not validate an application key. The production application-key path remains unfinished.

## Alternatives and trade-offs

These alternatives preserve the pre-approval discussion. The approved resolution below selects the current contract.

1. **Coordinate revocation and protected writes through the existing transaction.** Load current key facts with the operation’s authorization facts and coordinate conflicting revocation through a documented lock or conditional check. This gives a clear ordering point for database effects, but adds contention and requires a fixed lock order.
2. **Use versioned observations with explicit final checks.** Record the relevant observed key state and check it again at the agreed effect/disclosure boundary. This can reduce time holding locks, but every participating operation must honor the check. It cannot make a remote call atomic with PostgreSQL.

## Approved resolution

Verify the submitted secret, then check fresh stored key and account facts at the protected boundary. Earlier successful authentication is not a permission certificate.

Preserve ADR-0074: the verifier receives the complete credential and trusted installation/audience/adapter context. It returns only ApplicationKeyId and its associated PrincipalId, or the existing rejection/availability outcomes. The authentication service checks current account eligibility. Existing Access authorizers own current key, account, action and protected-source checks.

Use the database's current UTC time after acquiring the relevant coordination locks. A key is expired when check_time >= expires_at. Do not use the client's clock or a transaction-start timestamp that predates a long lock wait.

For protected database writes and admission, serialize the key check against revocation using transaction-scoped database locking. Hold the relevant lock through the local transaction. Revocation winning this ordering denies the protected effect. An already committed effect is not undone by later revocation. Implementers must use a consistent lock order with existing principal/resource coordination. Exact SQL, method names and schema representations remain ordinary implementation choices, subject to the repository's standards and review.

For protected reads, replayed results and streams, use a fresh authorization decision immediately before releasing the bounded protected result or next protected delivery unit. For external effects, authorize one bounded dispatch step immediately before dispatch and record its operation attribution. Do not hold database locks while waiting for the provider or network. This defines an authorization ordering point, not an atomic PostgreSQL/network transaction. Revocation after a step was authorized cannot recall bytes or requests already in flight. Later protected steps and disclosures require new authorization.

Database failures never become cached authorization success. Known rollbacks produce the existing bounded failure. An uncertain commit uses original-request recovery. Add no automatic business-command replay or paid-call retry.

## Decision trigger and stopping boundary

Apply this accepted contract when the affected implementation reaches its original trigger. Ordinary representation and method-name choices remain implementation work. A change to the selected policy requires a new explicit decision. Missing qualification limits claims, not authorized evidence gathering.

## Architectural impact and dependencies

Access verifier, authentication service, facts projections, authorizers and revocation workflow. Shared admission/replay callers and key request sequence diagrams must agree. No new public status code is implied.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](decision-admitted-work-authority.md). Only when the consumer admits or resumes durable background work.

## Implementation and required evidence

The following are required behavioral cases, not executed test results.

- Revoke after initial verification, before write authorization: deny the write.
- Write authorization/commit wins before revoke: retain the committed effect.
- Expiry occurs during a lock wait: evaluate the post-wait database time.
- A saved result exists but the presented key is revoked: deny protected replay.
- Verification is unavailable or canceled: no fallback and no cached success.

## Sources and finalization

- [Accepted key format and lifetime](application-key-contracts.md#application-key-contract).
- [Existing authorizers and remaining contracts](application-keys.md#application-key-current-authorization).
- [Minimal verifier split](../../../../docs/adr/ADR-0074-separate-application-key-verification-from-local-admission.md).
- [Evidence records](credential-and-recovery-records.md#authentication-evidence-records).

The approved resolution is recorded in [ADR-0100](../../../../docs/adr/ADR-0100-order-key-revocation-at-protected-boundaries.md). Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim runtime qualification.
