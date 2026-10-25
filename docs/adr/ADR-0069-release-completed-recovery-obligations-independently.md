# ADR-0069: Release completed recovery obligations independently

**Status:** Accepted. Partially supersedes [ADR-0058](ADR-0058-block-product-access-during-identity-recovery-cleanup.md) for overlapping recoveries and identities without local admission. Its provider-evidence, suspension and product-access requirements remain selected.

**Date:** 2026-10-23

## Context and Problem Statement

Alice can have two recovery checklists at once. Both may finish provider cleanup before either block is released. Requiring every other checklist to be released first would leave them waiting for each other indefinitely.

A verified Kratos identity can also recover before joining Inframeld. Its completed cleanup must not require creating an account merely to retire the obligation. Neither retiring that obligation nor completing a password reset establishes product admission or permissions.

ADR-0058 selected independent provider outcomes and an access block during cleanup. Its wording about no newer pending cleanup did not distinguish releasing this original obligation from authorizing product access across every obligation. This decision makes that distinction explicit.

## Considered Options

- Require no other unreleased obligation before releasing this one. This keeps a broad block but can leave fully cleaned overlapping recoveries waiting for each other.
- Release each completed original obligation independently, retaining all other blocks and normal account eligibility checks. This is selected.
- Keep completed cleanup blocked until a local account exists. This can retain a finished obligation indefinitely or make account provisioning a cleanup dependency.

The maintainer accepted independent release and completion without local account creation on the recorded decision date. Suspension and retirement remain restrictions on automatic release for linked accounts.

## Decision Outcome

After both Kratos and Hydra cleanup outcomes are confirmed, release only the original recovery's block when its linked account is an active human. If no local identity link exists, release the finished obligation without creating a principal, link, membership or grant. A suspended or retired account remains ineligible for automatic release.

Other unreleased obligations for the same installation/provider/subject continue blocking product access. A completion cannot release another flow's block. Two fully confirmed checklists can therefore finish independently. Product requests still verify current credentials, account state, all pending recovery blocks and operation permissions.

An already released repeat returns its recorded cleanup state and original operation identity without another save or provider call. An unreleased repeat may recheck current local eligibility, including after a separate authorized restoration. No completion changes account status or restores removed grants.

Application workflows own short transactions. For linked identities, current-state reads participate in the existing organization coordination. Provider calls remain outside transactions. Evidence authentication, callback delivery and safe external reconciliation retain their existing requirements.

## Consequences

- Cleanup can finish before local admission, and overlapping completed checklists do not deadlock on each other's release state.
- A released checklist is not an authorization certificate. Even a result reporting no other pending recovery is only an observation of that transaction.
- The existing admission table, per-flow aggregate and conditional repository save remain sufficient. No new schema or public API is introduced.
- Completion service and PostgreSQL tests qualify local state recording and coordination. Production callbacks, provider cleanup, bounded reconciliation and concurrent first-local-admission qualification remain unfinished.

## Links

- [Recovery behavior](../../.agents/skills/inframeld-access-models/references/recovery.md#identity-recovery-cleanup) and [completion workflow](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#recovery-completion-workflow).
- [Recovery records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records) and [cleanup reconciliation](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#identity-cleanup).
- [Release policy](../../apps/backend/src/inframeld_backend/access/domain/policies/identity_recovery_release_policy.py), [completion service](../../apps/backend/src/inframeld_backend/access/application/services/identity_recovery_completion_service.py) and [PostgreSQL scenarios](../../apps/backend/tests/integration/access/test_identity_recovery_completion_postgres.py).
