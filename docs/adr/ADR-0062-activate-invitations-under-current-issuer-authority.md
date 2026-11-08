# ADR-0062: Activate invitations under current issuer authority

**Status:** Accepted.

**Date:** 2026-10-04

## Context and Problem Statement

Alice invites Bob to join Support, then loses her assignment authority before Bob activates the invitation. A delayed invitation must not act as a permanent permission snapshot or merge Bob with another principal merely because their email addresses match.

## Considered Options

The reviewed proposal selected an expiring, revocable, single-use invitation with activation-time authority checks. No additional alternative was evaluated in this discussion.

## Decision Outcome

Use an opaque protected invitation intent with an operator-configured lifetime, seven days by default, and a configured maximum no greater than thirty days. Require authority for every intended effect at issuance and again at activation. Bind verified Ory authority/subject to the stable principal, never email matching. Save consumption and guarded local assignments with audit; replay resolves the original activation.

The [invitation contract](../../.agents/skills/inframeld-access-models/references/admission-and-invitations.md#invitations) owns current checks, effects and failure behavior. It records 32-random-byte digest-verified tokens and the narrow Kratos-cookie/CSRF admission operation for a not-yet-admitted recipient. Ordinary session dependencies requiring admission cannot serve that operation, and activation cannot restore suspension or release a recovery block. An invitation supplies neither identity proof nor an unrestricted invitation role. The implemented HTTP contract includes a non-consuming cookie/CSRF-protected scope preview for the recipient; it supplies no admission or ordinary product authority, and activation still rechecks current state.

[ADR-0130](ADR-0130-observe-private-kratos-password-verifiers-for-invitations.md), accepted on 2026-11-07, selects the narrow confidential Kratos observation for fresh activation's password-completion check. It preserves this authority/activation decision and ordinary identity-verification contracts. Its three configured real-Kratos verifier cases are qualified.

## Consequences

- Revoked, expired, consumed or stale/ineligible invitations cannot create assignments.
- Lost responses do not grant twice; revoking an already activated invitation does not remove its completed assignments.
- Ory onboarding and local assignment activation have separate outcomes.
- The [invitation HTTP contract](../../.agents/skills/inframeld-access-models/references/invitation-contracts.md#invitations-and-key-routes) is implemented through four registered routes and generated application clients, including show-once issuance and retained activation results. Token generation, digest-only storage and atomic Access-owned admission/assignments are implemented. Account UI, CLI, starter provisioning and future resource integrations retain their own owners and qualification.

## Links

- [Access identity and grants](../../.agents/skills/inframeld-access-models/references/memberships-groups-and-handover.md#sharing).
- [Logical invitation records](../../.agents/skills/inframeld-access-models/references/admission-and-invitations.md#invitation-records).
- [ADR-0014: current exact-target delegation](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md).
