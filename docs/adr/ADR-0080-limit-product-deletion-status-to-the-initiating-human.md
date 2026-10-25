# ADR-0080: Limit product deletion status to the initiating human

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Alice deletes Support. Cleanup removes relationships that ordinary Project job reads depend on, but she still needs to learn whether the original deletion finished. A content-free status result can meet that need without exposing the deleted Project.

The former broad deletion explanation permitted the original actor or an administrator. The narrower Access contract permitted the currently eligible original initiating human after membership removal. No general administrator status-viewing authority was defined. Keeping both formulations could cause an implementation to invent an administrative reading bypass.

This decision resolves only that viewer conflict within [PD-KNOWLEDGE-02](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md). The developer explicitly approved initiator-only product status and these documentation edits during the focused-reference restructure. Retention periods, exact status routes/representations and other unresolved questions remain pending.

## Considered Options

- Permit the currently eligible initiating human through the authoritative original principal/operation binding. This supplies narrow lost-response recovery without creating a new administrator role or reading permission.
- Extend status to additional explicitly authorized humans. This could help operational handover, but requires a separate concrete authority and lifecycle contract. Broad administrator wording alone cannot establish that contract.

## Decision Outcome

Only the currently eligible human who initiated deletion may use the product's retained content-free original-operation status. The server verifies current identity eligibility and the authoritative principal/operation binding. This narrow read remains available after ordinary Project membership is removed, within retention.

Administrator status alone grants no access. A claimed operation ID, previous membership or an earlier credential does not grant access. The status result exposes no private inventory, hidden names, private-content counts or excerpts. It grants neither cancellation nor continuation, restores no resource and does not bypass credential expiry, revocation, suspension or recovery restrictions.

For example, Alice can inspect her original deletion if she is still eligible. Bob cannot inspect it solely because he administers the installation. If Alice is suspended, retired or otherwise ineligible, this exception does not make her eligible. Separate authorized host operations do not become a public credential fallback.

This supplements [ADR-0039](ADR-0039-block-access-before-resumable-physical-deletion.md). It does not change admission authority, original-scope cleanup or the distinction between blocking access and completing physical erasure. No new endpoint, action identifier, status enum, schema or runtime implementation is selected here.

## Consequences

- Cleanup can remove Project membership without preventing an eligible initiator from recovering the safe result.
- Other administrators cannot acquire access through a broad role label. Broader product inspection would need a later explicitly approved design.
- Expiry, lost identity eligibility and unavailable authoritative operation history still limit recovery. The system must report those limits rather than silently broadening readers.
- Acceptance is not runtime qualification. Status routes and retention still require their owning implementation decisions and tests.

## Links

- [Project deletion](../../.agents/skills/inframeld-knowledge/references/project-deletion.md).
- [Access grant and deletion transport boundaries](../../.agents/skills/inframeld-access-models/references/grant-contracts.md).
- [Pending retention work](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md).
