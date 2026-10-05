# ADR-0062: Activate invitations under current issuer authority

**Status:** Accepted.

**Date:** 2026-10-04

## Context and Problem Statement

Alice invites Bob to join Support, then loses her assignment authority before Bob activates the invitation. A delayed invitation must not act as a permanent permission snapshot or merge Bob with another principal merely because their email addresses match.

## Considered Options

The reviewed proposal selected an expiring, revocable, single-use invitation with activation-time authority checks. No additional alternative was evaluated in this discussion.

## Decision Outcome

Use an opaque protected invitation intent with a seven-day default and thirty-day maximum, both operator-configurable. Require authority for every intended effect at issuance and again at activation. Bind verified Ory authority/subject to the stable principal, never email matching. Save consumption and guarded local assignments with audit; replay resolves the original activation.

The [invitation contract](../development/access-contracts.md#invitations) owns current checks, effects and failure behavior. It records 32-random-byte digest-verified tokens and the narrow Kratos-cookie/CSRF admission operation for a not-yet-admitted recipient. Ordinary session dependencies requiring admission cannot serve that operation, and activation cannot restore suspension or release a recovery block. An invitation supplies neither identity proof nor an unrestricted invitation role. The concrete HTTP draft includes a non-consuming cookie/CSRF-protected scope preview for the recipient; it supplies no admission or ordinary product authority, and activation still rechecks current state.

## Consequences

- Revoked, expired, consumed or stale/ineligible invitations cannot create assignments.
- Lost responses do not grant twice; revoking an already activated invitation does not remove its completed assignments.
- Ory onboarding and local assignment activation have separate outcomes.
- The [HTTP draft](../development/access-contracts.md#http-operation-matrix) now supplies new public declarations and secret/activation replay fields for final review. Provider integration still needs qualification. Token generation/digest-only storage and the narrow admission boundary are accepted contracts.

## Links

- [Access identity and grants](../development/access-control.md#sharing).
- [Logical invitation records](../development/data-model.md#invitation-records).
- [ADR-0014: current exact-target delegation](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md).
