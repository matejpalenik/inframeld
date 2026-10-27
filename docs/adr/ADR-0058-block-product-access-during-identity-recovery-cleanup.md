# ADR-0058: Block product access during identity-recovery cleanup

**Status:** Accepted. Partially superseded by [ADR-0069](ADR-0069-release-completed-recovery-obligations-independently.md) for independent per-flow release and completion before local admission, and by [ADR-0070](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) for bulk Hydra scope and delayed-attempt effects. Deliberate suspension restoration remains required. The decision originally clarified recovery completion under ADR-0019 and ADR-0053.

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

Deduplicate completed trusted events by their original identity. A duplicate cannot revoke credentials from later logins, and an older operation cannot release a newer block. The temporary obligation does not introduce a new `PrincipalStatus` or cache permissions in `AccessContextDTO`. Detailed procedures belong to [Access](../../.agents/skills/inframeld-access-models/references/recovery.md#identity-recovery-cleanup); records and retry semantics belong to [the data model](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records) and [jobs](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#identity-cleanup).

## Consequences

[ADR-0069](ADR-0069-release-completed-recovery-obligations-independently.md) refines the historical no-newer-pending-cleanup wording above. A completed eligible flow may release only its own block while other unreleased flows continue blocking product access. A fully cleaned identity without a local account may finish without provisioning one. The provider-evidence, suspension and no-permission-restoration rules remain unchanged.

[ADR-0070](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) replaces the stronger later-login-preservation requirement for Hydra recovery cleanup. Unfinished bulk retries and already-dispatched calls may invalidate newer CLI credentials. Completed events still initiate no new cleanup, and the legitimate Kratos recovery session remains protected. The original rationale above is retained as historical context.

[ADR-0081](ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) selects native recovery and password-settings hooks as the evidence source, followed by independent Hydra cleanup. It distinguishes recovery-code acceptance from saved-password and native-revocation evidence. [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) resolves the versioned evidence, association and reconciliation contract. Production delivery and qualification remain unfinished. This refines the integration approach without changing the release or suspension rules above.

- Product access fails closed during partial cleanup while routine recovery can finish without an extra administrator intervention.
- Emergency suspension retains its immediate block, preserved-but-unusable assignments and deliberate security-review restoration rule.
- [The private callback contract](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#recovery-callbacks) records the dedicated service secret, bounded allowlisted inputs and stable native-flow/event-type identity. The [version 2 private evidence contract](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#recovery-wire) specifies accepted evidence and receipt requirements. Hook ordering, delivery/reconciliation evidence and recovery-session preservation need pinned-release #117 qualification. Current upstream hook observations do not establish deployed behavior.
- Existing recovery tests establish identity-flow boundaries, not complete Kratos/Hydra cleanup or automatic block release. This decision changes no runtime configuration, code or schema.

[ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) also permits a new verified recovery to supply combined proof for explicitly linked older operations. Each original checklist retains its own release checks. This refines evidence provenance without permitting an older completion to clear a newer block.

## Links

- [ADR-0019: emergency suspension and scoped recovery](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md).
- [ADR-0053: Kratos/Hydra CLI authentication](ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md).
- [Access implementation and qualification](../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication).
- [#116: Access contracts](https://github.com/matejpalenik/inframeld/issues/116), [#117: identity integration](https://github.com/matejpalenik/inframeld/issues/117).
