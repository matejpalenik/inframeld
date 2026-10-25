# PD-ACCESS-03: Prove recovery cleanup before releasing product access

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract and production qualification.

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

Alice resets her password. Kratos accepts a recovery code before her new password is saved. Meanwhile an older CLI consent or refresh may complete. Two successful Hydra cleanup responses do not by themselves prove that password replacement, session cleanup and all required CLI invalidation are complete. Releasing Alice’s block too early would reopen product access on incomplete evidence.

The integration shape is accepted, but production has not wired the complete trusted evidence and reconciliation path. The internal completion service accepts provider outcomes from its caller. That caller must establish what the outcomes mean. An authenticated generic webhook proves its sender, not that every cleanup obligation has succeeded.

## Accepted context and evidence

Preserve authenticated original-flow registration, native Kratos cleanup, independent durable Hydra cleanup and the product block during the password-setting gap. Private callbacks retain their dedicated rotatable secret, five-field allowlisted bounded body and original-flow/event/phase deduplication. The local aggregate and completion service already implement a subset.

Credential generations prevent stale human CLI credentials from becoming valid again inside Inframeld. They do not prove Hydra cleanup or legitimate-session preservation. Each original recovery releases only its own obligation. Provider calls remain outside SQL transactions. Delayed bulk cleanup can invalidate newer credentials, as already accepted.

## Alternatives and trade-offs

1. **Complete from trusted native events plus durable reconciliation.** Bind authenticated callbacks to the registered flow and verify their required meaning, then reconcile unfinished independent cleanup. This provides prompt progress when callbacks arrive, but demands careful event ordering and trustworthy native completion evidence.
2. **Require an explicit private completion verification step.** Treat callbacks as observations and perform a bounded trusted confirmation before recording aggregate provider completion. This makes the evidence gate visible, but adds a private integration step and cannot rely on ordinary generic webhook success.

## Non-binding recommendation

**Proposal only.** Prefer registered-flow evidence with bounded durable reconciliation, keeping callback authentication separate from evidence qualification. Use the pinned provider sequence to decide exactly which native signal and checks establish completion. Neither alternative may replace provider cleanup with generation checks alone.

## Decision trigger and stopping boundary

Before wiring production recovery admission/completion callbacks, cleanup orchestration, issuance coordination or block release.

The unresolved completion mechanism gates dependent production wiring. Existing local checklist tests and provider qualification experiments may proceed without inventing successful completion.

## Architectural impact and dependencies

Access recovery coordinator, private callback validation, Kratos settings/recovery integration, Hydra cleanup and consent/refresh coordination, shared jobs and recovery sequence diagrams. No new public recovery API is selected here.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-04: Coordinate first account admission with identity recovery](decision-recovery-first-admission.md). When the identity has no local account or first admission overlaps cleanup.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](decision-admitted-work-authority.md). When recovery must stop already-admitted product work.

## Open questions and required evidence

- What exact trusted evidence proves password replacement and native session cleanup?
- When can the aggregate Hydra outcome be called confirmed despite overlapping issuance?
- How are lost acknowledgments, restarts and overlapping flows reconciled?
- What bounded deadline/backoff and operator action avoid indefinite unexplained blocking?

## Sources and finalization

- [Recovery and provider observations](recovery.md#identity-recovery-cleanup).
- [Private callback contract](private-recovery-handoff.md#recovery-callbacks).
- [Private recovery handoff](private-recovery-handoff.md#recovery-wire).
- [Independent release](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md).
- [Bulk Hydra cleanup](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
