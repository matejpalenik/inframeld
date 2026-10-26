# ADR-0085: Bind password-settings evidence to original recoveries

**Status:** Accepted design. Partially supersedes ADR-0081's unchanged five-field envelope and refines ADR-0069's evidence provenance. Private delivery is implemented under ADR-0086. Provider execution and host continuation remain unfinished.

**Date:** 2026-10-25

## Context and Problem Statement

Alice proves a recovery code, then restarts password settings. Kratos creates a different settings-flow ID. A callback can also be lost after the password was saved and old sessions were removed. Inframeld needs to know which original checklist that later evidence belongs to, without trusting an ID supplied by the browser.

The five-field version 1 draft cannot express the settings/session association. It was never a delivered production interface. The developer approved a versioned evidence contract and permitted a newer verified recovery to supply evidence for older unfinished obligations of the same identity. The approved #242 plan records the remaining delivery, retry and maintenance contracts in their owning references.

## Considered Options

- Keep the five-field envelope and require the original settings path and evidence. This is smaller, but cannot reliably recover an expired association or missing completion evidence.
- Bind native settings flows and sessions durably to the original recovery, with separate code-verification, association and password-saved evidence. Allow a newer recovery to cover explicitly linked older obligations. This requires additional provenance records, but supports restarted flows without inventing provider success.
- Require an operator to force completion when evidence is missing. This would substitute operator authority for password/session evidence and is not selected.

## Decision Outcome

Choose the version 2 private evidence contract in [the private handoff](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#recovery-wire). Keep dedicated sender authentication, strict bounded parsing and server-owned installation/provider scope. Native recovery admission still creates the original obligation, block and credential-version advancement atomically.

The settings-flow creation hook associates native settings-flow/session IDs with an already admitted recovery only through the native recovery-created context and matching identity. A restarted settings flow may inherit that checked association through the same session and identity. A query parameter on an ordinary settings request establishes nothing. Only the post-persistence password hook, after native session revocation, supplies Kratos completion evidence. Callback acknowledgment means durable receipt, not release.

When a new recovery is first admitted, record explicit links to older unfinished obligations for that exact installation/provider/subject under identity coordination. Its later complete Kratos and Hydra evidence may satisfy those linked obligations. Recheck and save each original checklist separately. Preserve original operation identities, history, confirmed progress and local eligibility rules. This does not authorize an older completion to clear a newer obligation, a blanket identity unblock or a retry-budget reset.

Lost acknowledgments replay recorded receipts. Missing completion evidence is never inferred from a successful form, settings status or elapsed time. A further password save through the trusted session association can supply fresh evidence. If that session is unavailable, a new verified recovery can provide the explicitly linked proof. Host maintenance cannot manufacture it.

## Consequences

- Evidence receipts, flow/session associations and links to covered original operations become durable Access records. They are not a credential inventory. No cookie, password or token is retained.
- The original per-flow aggregate and current release policy remain responsible for each checklist. Applying newer proof is application orchestration, not a reason to merge identities or move provider calls into entities.
- [The completion workflow](../../.agents/skills/inframeld-access-models/references/recovery-completion.md) owns durable attempts, exact failure mapping and the accepted twelve-attempt/one-hour run budget. Both scoped Hydra acknowledgments are required. Old-version credentials remain unusable at Inframeld, even if Hydra issues them late.
- The [host continuation contract](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#recovery-cleanup-continuation) uses the original recovery and a unique operator request ID. No reviewed-run ID is required. Current-state checks, request deduplication and the active-run prohibition still apply.
- #243 must qualify the native association, #244 must qualify durable execution and release, and #245 must qualify operator continuation. Accepting this specification supplies no runtime evidence and changes no production configuration or schema.

## Links

- [Resolved PD-ACCESS-03 and qualification matrix](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md).
- [Evidence and run records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#recovery-delivery-records).
- [ADR-0058: Recovery block](ADR-0058-block-product-access-during-identity-recovery-cleanup.md), [ADR-0069: Independent release](ADR-0069-release-completed-recovery-obligations-independently.md) and [ADR-0070: Bulk Hydra cleanup](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md).
- [ADR-0072: Credential versions](ADR-0072-version-human-cli-credentials-across-account-recovery.md), [ADR-0081: Native hooks](ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md), [ADR-0082: Identity coordination](ADR-0082-coordinate-first-admission-and-recovery-by-identity.md), [ADR-0083: Retry budget](ADR-0083-bound-hydra-recovery-cleanup-retries.md) and [ADR-0084: Host continuation](ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md).
- Pinned Kratos [settings hooks](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go), [settings-flow creation](https://github.com/ory/kratos/blob/v26.2.0/selfservice/flow/settings/handler.go) and [recovery-to-settings transition](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/code/strategy_recovery.go). Source inspection supports the chosen seams, not finished runtime qualification.

Implementation note: the [private notification process](ADR-0086-serve-recovery-notifications-through-a-private-backend-process.md) now saves native evidence and the original cleanup handoff. [Its owning implementation reference](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#implemented-private-delivery) separates that boundary from unfinished Hydra execution, proof propagation and release.
