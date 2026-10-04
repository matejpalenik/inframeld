# ADR-0058: Block product access during identity-recovery cleanup

**Status:** Accepted; clarifies recovery completion under ADR-0019 and ADR-0053. Deliberate suspension restoration remains required.

**Date:** 2026-10-04

## Context and Problem Statement

Alice completes verified password recovery. Old Kratos sessions and affected Hydra grants must be invalidated, but the two providers can fail independently. A completed password form cannot prove both cleanup outcomes. Alice may be an otherwise active user, or an already suspended compromised user; treating both as permanent suspension would conflate routine recovery with incident restoration.

## Considered Options

- Keep product access blocked until a human deliberately restores every recovered user, including otherwise active accounts. This requires manual intervention for routine recovery.
- Use a temporary product-access block for verified recovery cleanup. Release it automatically for an otherwise active eligible account after both required outcomes are confirmed, while preserving separate deliberate restoration of suspended accounts.

These are the recovery-release alternatives reviewed. A particular Kratos hook implementation was not qualified by this decision.

## Decision Outcome

Authenticated server-side, flow-bound evidence of verified recovery/reset durably admits one original cleanup operation and temporary product block. Proof of the verified reset is distinct from confirmation of the subsequent Kratos/Hydra cleanup outcomes; exact callback ordering remains to qualify. Anonymous email requests, UI redirects and OAuth callbacks cannot supply that evidence. Recovery/password-setting UI remains usable, and the legitimate new recovery session must be preserved.

Record Kratos-session cleanup and affected Hydra-grant cleanup independently. Failed or uncertain required outcomes keep the block. Use bounded reconciliation outside database transactions; success at one provider is not proof of success at the other.

After both outcomes are confirmed, release this operation's block only if the human is otherwise currently active/eligible and no newer cleanup remains pending. A suspended human still requires an authorized Restore users operation, verification of the same legitimate identity, security review and confirmed cleanup/current state. Neither path recreates removed memberships or grants.

Deduplicate completed trusted events by their original identity. A duplicate cannot revoke credentials from later logins, and an older operation cannot release a newer block. The temporary obligation does not introduce a new `PrincipalStatus` or cache permissions in `AccessContextDTO`. Detailed procedures belong to [Access](../development/access-control.md#identity-recovery-cleanup); records and retry semantics belong to [the data model](../development/data-model.md#identity-cleanup-records) and [jobs](../development/jobs-and-idempotency.md#identity-cleanup).

## Consequences

- Product access fails closed during partial cleanup while routine recovery can finish without an extra administrator intervention.
- Emergency suspension retains its immediate block, preserved-but-unusable assignments and deliberate security-review restoration rule.
- [The private callback contract](../development/access-contracts.md#recovery-callbacks) records the dedicated service secret, bounded allowlisted inputs and stable flow/event/phase identity. The [version 1 private draft](../development/access-contracts.md#recovery-wire) now specifies declarations/evidence requirements for final review; hook ordering, delivery/reconciliation evidence and recovery-session preservation need pinned-release #117 qualification. Current upstream hook observations do not establish deployed behavior.
- Existing recovery tests establish identity-flow boundaries, not complete Kratos/Hydra cleanup or automatic block release. This decision changes no runtime configuration, code or schema.

## Links

- [ADR-0019: emergency suspension and scoped recovery](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md).
- [ADR-0053: Kratos/Hydra CLI authentication](ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md).
- [Access implementation and qualification](../development/access-control.md#implemented-human-authentication).
- [#116: Access contracts](https://github.com/matejpalenik/inframeld/issues/116), [#117: identity integration](https://github.com/matejpalenik/inframeld/issues/117).
