# PD-ACCESS-02: Keep durable work and credential lifetime explicit

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Architecture and implementation contract.

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

SupportBot starts an evaluation using K1. A worker continues after the CLI watcher disconnects. Alice rotates to K2, K1 expires, and later she revokes K1 after suspecting a leak. Bob also removes SupportBot’s Query grant. The worker needs explicit rules for these different events, not one accidental “original token is still valid” check.

Accepted work survives its original request, while current authority remains mandatory. The design has not selected whether credential expiry, rotation or revocation terminates already-admitted work, nor how replacement credentials recover it. A human access token can expire during a long build too. Guessing can either strand ordinary jobs or let compromised work continue beyond its intended authority.

## Accepted context and evidence

Stable principal attribution, current account eligibility, recovery blocks, exact permissions, current source access and no hidden paid retry remain requirements. An operation identity and fingerprint preserve what was requested, not a reusable permission certificate. Disconnecting a watcher does not cancel accepted work.

ADR-0074 settles incoming verification ownership and expressly leaves admitted-job lifetime open. A remote request already sent cannot be recalled. Keep incoming application keys, human OAuth tokens and outgoing provider secrets distinct.

## Alternatives and trade-offs

1. **Use principal-based authority after durable admission.** Expiry or ordinary rotation affects new incoming requests, while workers repeatedly check current principal/resource authority. This avoids coupling hours of work to a short-lived token, but key revocation alone would not necessarily stop already-admitted work. Explicit cancellation/suspension semantics must address that risk.
2. **Bind continuation to the original credential.** Workers also require original credential currentness. Revocation can stop later protected steps, but ordinary expiry/rotation can interrupt legitimate jobs. Human renewal and explicit resume need a safe, specified path.
3. **Distinguish ordinary expiry from deliberate revocation.** Allow documented continuation after expiry/rotation but stop on an explicit invalidation event. This may fit operations better, but introduces additional state and event semantics that need clear ownership.

## Non-binding recommendation

**Proposal only.** Prefer separating request authentication from durable job authority, then decide the deliberate-revocation response explicitly. Compare the options using a long evaluation and a compromised bot key before accepting any continuation rule. Do not treat this preference as permission for an existing job to continue.

## Decision trigger and stopping boundary

Before admitting, executing or resuming durable work that must interpret credential expiry, rotation, revocation or replacement.

Pause the affected admission/execution/recovery contract. Do not block unrelated authentication or existing synchronous commands.

## Architectural impact and dependencies

Access authority facts, shared jobs/checkpoints, cancellation and recovery, Pipeline builds, Evaluation, source sync and release publication. Worker sequences must show admission, later checks and already-sent effects separately.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-01: Check application-key currentness at the right boundary](decision-key-currentness.md). When the initiating or recovering request uses an application key.
- [PD-CONTRACTS-05: Qualify cleanup and recovery under a full bounded queue](../../inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md). When job claim/checkpoint behavior affects how quickly restrictions can take effect.

## Open questions and required evidence

- Which events stop queued work, later sends, commits and disclosures?
- May K2 recover an operation admitted by K1 for the same principal?
- What is the human-token expiry rule?
- How do suspension, recovery and removed source/action grants override continuation?
- What does the operator do about already-dispatched unknown work?

## Sources and finalization

- [Explicit remaining credential contract](../../../../docs/development/access-control.md#application-key-current-authorization).
- [Admission and checkpoints](../../../../docs/development/jobs-and-idempotency.md#admission).
- [Uncertain remote work](../../../../docs/development/jobs-and-idempotency.md#uncertain).
- [Versioned human credentials](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
