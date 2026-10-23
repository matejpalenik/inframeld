# ADR-0070: Use bulk Hydra revocation for identity recovery

**Status:** Accepted. Partially supersedes [ADR-0058](ADR-0058-block-product-access-during-identity-recovery-cleanup.md) on Hydra cleanup scope and preservation of later CLI logins. Its recovery block and provider-evidence rules remain selected. [ADR-0069](ADR-0069-release-completed-recovery-obligations-independently.md) continues to govern per-flow release.

**Date:** 2026-10-23

## Context and Problem Statement

Alice resets her password. Her earlier CLI credentials must stop working, while Bob's credentials remain valid. The previous approach revoked individual grants and remembered logins so that even a delayed retry preserved Alice's newer credentials.

Pinned Hydra observations show that consent listing omits working skipped-consent grants and can be empty while a remembered login remains usable. Preserving every later login would therefore require a separate, complete target-capture mechanism and coordination with issuance. The developer accepts another CLI sign-in after delayed cleanup in exchange for simpler recovery.

## Considered Options

- Retain targeted cleanup and capture every required grant/login identity durably. This preserves later logins but adds inventory and lifecycle coordination.
- Use subject-scoped bulk cleanup and accept that delayed attempts can invalidate newer CLI credentials. This is selected.

## Decision Outcome

Use separate Hydra operations to revoke the affected subject's grants for `inframeld-cli` and forget all of that subject's Hydra remembered logins. The latter API has no client filter. Neither operation may broaden to another human or to client-wide deletion. The caller establishes the original subject's installation/provider binding before invoking the adapter.

An unfinished retry may revoke Alice's newer credentials, requiring another login. A call already dispatched may also finish after timeout, cancellation or local completion. A durably completed event must not initiate new cleanup, but deduplication cannot recall an in-flight provider request. Keep reconciliation bounded and tied to the original obligation.

Preserve the legitimate Kratos recovery browser session. Ordinary selected-device CLI logout retains its narrower semantics. No per-login inventory, original-target snapshot or timestamp cutoff is required for this recovery design.

## Consequences

- Recovery uses the provider's bulk operations without duplicating its token inventory.
- Alice may need to authenticate again, and CLI work can fail until she does. Bob remains unaffected.
- Kratos and Hydra outcomes remain independent. One acknowledged request does not establish complete recovery cleanup or permission to release a block.
- The standalone adapter performs bounded provider I/O without database work or automatic retries. Existing recovery admission, checklist persistence and local release rules remain unchanged.
- Production callbacks, durable execution/reconciliation and coordination with authorization-code issuance and refresh remain unfinished. Provider tests do not qualify the account UI or complete CLI lifecycle.

## Links

- [Access behavior and provider evidence](../development/access-control.md#hydra-cleanup-evidence).
- [Recovery records](../development/data-model.md#identity-cleanup-records) and [reconciliation](../development/jobs-and-idempotency.md#identity-cleanup).
- [Hydra v26.2.0 handlers](https://github.com/ory/hydra/blob/v26.2.0/consent/handler.go) and [bulk persistence](https://github.com/ory/hydra/blob/v26.2.0/persistence/sql/persister_consent.go).
