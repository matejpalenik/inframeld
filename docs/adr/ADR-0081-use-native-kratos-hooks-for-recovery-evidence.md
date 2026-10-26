# ADR-0081: Use native Kratos hooks for recovery evidence

**Status:** Accepted for native-hook integration. Partially superseded by [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) for the versioned evidence envelope and original-flow association. The production contract is resolved, with runtime delivery unfinished.

**Date:** 2026-10-25

## Context and Problem Statement

Alice enters a valid recovery code, then saves a replacement password. Those are separate steps. Inframeld must block product access during the gap and receive trustworthy evidence that the replacement was saved and native browser-session cleanup succeeded. Hydra cleanup is a separate obligation.

[ADR-0058](ADR-0058-block-product-access-during-identity-recovery-cleanup.md) already requires trusted evidence and a temporary recovery block. [PD-ACCESS-03](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md) asks how production obtains that evidence. The developer approved native hooks after reviewing current Ory documentation and the pinned Kratos/Hydra v26.2.0 source. This decision records that choice without claiming production wiring is implemented.

## Considered Options

- Use authenticated native Kratos events, bound to the original recovery, plus durable reconciliation of unfinished cleanup. This uses the provider's password and session lifecycle, but requires careful callback placement and delivery handling.
- Treat callbacks only as observations and add a separate private completion-verification step. This adds another integration boundary and still needs reliable provider evidence.

## Decision Outcome

Choose native Kratos hooks plus durable reconciliation. The accepted sequence is:

1. After Kratos verifies the recovery code, its recovery webhook durably admits the original obligation and product block. Admission advances the CLI credential version once. Code acceptance does not confirm password replacement.
2. Kratos saves the replacement through its password-settings flow and runs native `revoke_active_sessions`, preserving the session used to change the password.
3. An authenticated password-settings webhook runs after persistence and after native revocation. Its evidence must match the original admitted recovery and verified identity. A recovery webhook or pre-save settings callback cannot substitute.
4. Inframeld performs the separate Hydra CLI-grant and remembered-login cleanup calls outside database transactions. It records their outcomes durably and releases only an eligible original checklist after all required evidence is confirmed.

There is no single provider event certifying completion across Kratos, Hydra and Inframeld. This original decision retained the five-field draft. [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) replaces that envelope with three versioned evidence alternatives while preserving sender authentication. [The private handoff](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#native-hook-evidence) owns the evidence meanings. [Provider observations](../../.agents/skills/inframeld-access-models/references/recovery-provider-cleanup.md#documented-native-hook-support) distinguish documented capability, source inspection and earlier runtime tests.

## Consequences

- Kratos owns password replacement and native session revocation. Inframeld owns durable receipt, independent Hydra cleanup and local release checks.
- Missing or uncertain evidence keeps the block. A failed callback after persistence does not roll back the password change. Delivery loss must not be interpreted as failed password replacement or successful recovery completion.
- Original association, loss/restart reconciliation and completion are now resolved by [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) and the owning references. Retry/operator rules are recorded in ADR-0083/0084. ADR-0082 resolves first-account coordination, whose full admission integration remains unfinished.
- Bulk retry effects, permanent rejection of older CLI versions, independent per-flow release and protection of the legitimate Kratos session remain unchanged. No production token hook is selected.
- No application code, provider configuration or production completion wiring is introduced by this documentation decision.

## Links

- [Recovery workflow](../../.agents/skills/inframeld-access-models/references/recovery.md#identity-recovery-cleanup) and [completion coordination](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#track-cleanup-separately-from-access-restoration).
- [ADR-0069: Independent release](ADR-0069-release-completed-recovery-obligations-independently.md), [ADR-0070: Bulk Hydra cleanup](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) and [ADR-0072: Credential versions](ADR-0072-version-human-cli-credentials-across-account-recovery.md).
- [Ory hook documentation](https://www.ory.com/docs/kratos/hooks/configure-hooks), [session revocation](https://www.ory.com/docs/actions/revoke-active-sessions) and [Hydra revocation API contracts](https://github.com/ory/hydra/blob/v26.2.0/consent/handler.go#L58-L288).

Implementation note: the [private notification process](ADR-0086-serve-recovery-notifications-through-a-private-backend-process.md) now saves native evidence and the original cleanup handoff. [Its owning implementation reference](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#implemented-private-delivery) separates that boundary from unfinished Hydra execution, proof propagation and release.
