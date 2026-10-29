# PD-ACCESS-02: Keep durable work and credential lifetime explicit

**Status:** ACCEPTED on 2026-10-29 in [ADR-0101](../../../../docs/adr/ADR-0101-authorize-admitted-jobs-by-current-principal.md). Implementation and qualification remain pending.

**Owner:** `inframeld-access-models`

**Issue kind:** Architecture and implementation contract.

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

SupportBot starts an evaluation using K1. A worker continues after the CLI watcher disconnects. Alice rotates to K2, K1 expires, and later she revokes K1 after suspecting a leak. Bob also removes SupportBot’s Query grant. The worker needs explicit rules for these different events, not one accidental “original token is still valid” check.

Accepted work survives its original request, while current authority remains mandatory. At the time of the original analysis, credential expiry, rotation, revocation and replacement during admitted work had no selected contract. A human access token can expire during a long build too. Guessing can either strand ordinary jobs or let compromised work continue beyond its intended authority.

## Accepted context and evidence

Stable principal attribution, current account eligibility, recovery blocks, exact permissions, current source access and no hidden paid retry remain requirements. An operation identity and fingerprint preserve what was requested, not a reusable permission certificate. Disconnecting a watcher does not cancel accepted work.

ADR-0074 settles incoming verification ownership. This later resolution fills the admitted-job lifetime question it left open. A remote request already sent cannot be recalled. Keep incoming application keys, human OAuth tokens and outgoing provider secrets distinct.

## Alternatives and trade-offs

These alternatives preserve the pre-approval discussion. The approved resolution below selects the current contract.

1. **Use principal-based authority after durable admission.** Expiry or ordinary rotation affects new incoming requests, while workers repeatedly check current principal/resource authority. This avoids coupling hours of work to a short-lived token, but key revocation alone would not necessarily stop already-admitted work. Explicit cancellation/suspension semantics must address that risk.
2. **Bind continuation to the original credential.** Workers also require original credential currentness. Revocation can stop later protected steps, but ordinary expiry/rotation can interrupt legitimate jobs. Human renewal and explicit resume need a safe, specified path.
3. **Distinguish ordinary expiry from deliberate revocation.** Allow documented continuation after expiry/rotation but stop on an explicit invalidation event. This may fit operations better, but introduces additional state and event semantics that need clear ownership.

## Approved resolution

After durable admission, a product job belongs to its original principal, installation, scope and fixed inputs. It does not require the original raw credential to remain alive. Disconnect, normal human-token expiry, application key expiry, replacement and individual key revocation do not automatically cancel an already admitted job.

IMPORTANT CONSEQUENCE: revoking a key blocks new incoming requests through that key. It does not, by itself, cancel already accepted work. To contain a compromised application and its accepted jobs, revoke the key and use existing authorized job cancellation or application-account suspension. Suspension intentionally affects that account's other keys and jobs too.

Workers must use a durable-admission authority contract built from server-owned operation facts and current worker ownership/fence. They must not forge an incoming authentication context, retain raw credentials, or set a boolean to skip checks. The contract fixes original principal, installation/scope, admitted action/input meaning and applicable original human security generation. Existing Access policies still evaluate current account, recovery restrictions, required grants and source permissions before each protected step, business commit, publication and disclosure. A saved admission does not grant future new actions or inputs.

Cancellation stops eligible remaining work at existing bounded checkpoints. Suspension, retirement, recovery blocks, a changed human recovery generation, resource deletion or lost required authority prevent subsequent protected steps. A normal human sign-out or token expiry alone does not cancel accepted work.

On an authority failure, retain the existing job lifecycle: a known stopped failure is failed with a safe authority-change reason, not a new paused state. Unknown external effects remain recovery_required. Preserve confirmed progress and necessary accounting observations under current retention/erasure rules. Do not expose or publish protected results without current authority. Restoring permission does not silently restart the job.

A fresh valid credential for the same principal may inspect the original work under current read authority and explicitly request eligible continuation. Continuation rechecks current authority, keeps the original job/input/checkpoints and records fresh continuation authority, including a current human security generation when applicable. It never transfers ownership by substituting a new principal or repeats a paid call whose earlier outcome is unknown. Other actors retain only their separately accepted management permissions.

Trusted system recovery and erasure obligations are a separate boundary. They continue under their original narrowly authorized obligation even when product access is blocked. They cannot be turned into a route for normal product work.

## Decision trigger and stopping boundary

Apply this accepted contract when the affected implementation reaches its original trigger. Ordinary representation and method-name choices remain implementation work. A change to the selected policy requires a new explicit decision. Missing qualification limits claims, not authorized evidence gathering.

## Architectural impact and dependencies

Access authority facts, shared jobs/checkpoints, cancellation and recovery, Pipeline builds, Evaluation, source sync and release publication. Worker sequences must show admission, later checks and already-sent effects separately.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-01: Check application-key currentness at the right boundary](decision-key-currentness.md). When the initiating or recovering request uses an application key.
- [PD-CONTRACTS-05: Qualify cleanup and recovery under a full bounded queue](../../inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md). When job claim/checkpoint behavior affects how quickly restrictions can take effect.

## Implementation and required evidence

The following are required behavioral cases, not executed test results.

- Expiry or key replacement during a job does not cancel otherwise authorized work.
- Revoked K1 cannot poll, resume or create more work. Valid K2 must pass new checks.
- Suspension, lost grants or a recovery-generation change prevent later protected work and do not automatically resume when the restriction disappears.
- Already sent external work is not described as recalled, rolled back or safely repeatable merely because the worker loses authority.
- Recovery/erasure housekeeping cannot be disabled through an expired origin token.

## Sources and finalization

- [Explicit remaining credential contract](application-keys.md#application-key-current-authorization).
- [Admission and checkpoints](../../inframeld-application-contracts/references/jobs-and-recovery.md#admit-work-and-claim-an-attempt).
- [Uncertain remote work](../../inframeld-application-contracts/references/jobs-and-recovery.md#uncertain).
- [Versioned human credentials](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md).

The approved resolution is recorded in [ADR-0101](../../../../docs/adr/ADR-0101-authorize-admitted-jobs-by-current-principal.md). Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim runtime qualification.
