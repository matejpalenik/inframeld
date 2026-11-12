# ADR-0127: Fence human authentication evidence at restoration

**Status:** Accepted. Partially supersedes [ADR-0072](ADR-0072-version-human-cli-credentials-across-account-recovery.md) for the credential-version advancement trigger and [ADR-0073](ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md) for browser evidence and its currentness checks. Existing recovery semantics remain selected. Captured browser evidence, neutral current-facts checks and linked-human consent guards are implemented. The suspension and restoration transactions, provider deletion and cleanup jobs are implemented. The selected local PostgreSQL and pinned Ory qualification passed. Final hosted checks and human acceptance remain separate.

**Date:** 2026-11-05

## Context and Problem Statement

Alice's browser request passes Kratos verification, then pauses before application authorization. Bob suspends Alice, the required original cleanup completes, and an authorized human deliberately restores the same reviewed legitimate identity. With identity-only browser evidence, the paused request can see an active principal and use retained grants.

[ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md) requires deliberate restoration after security review. [ADR-0058](ADR-0058-block-product-access-during-identity-recovery-cleanup.md) keeps cleanup and independent recovery blocks separate. ADR-0072 advances the identity version for genuine recovery, while ADR-0073's original browser evidence carries only identity. Those choices do not select a restoration cutover. This decision selects a limited application-evidence fence, with the late-session limitation below explicitly accepted.

## Considered Options

- Require genuine recovery proof for every restoration, together with correct browser evidence ordering. This adds a mandatory recovery journey and completion coordination. It does not independently exclude every late-created Kratos session.
- Advance the existing identity version on an actual authorized restoration and bind browser evidence before final verification. This is selected. It reuses the existing security state without manufacturing recovery evidence or maintaining a session inventory.
- Keep restoration stopped until a stronger provider/session cutover contract is selected. This would be necessary if the explicitly accepted limitation were unacceptable. No universal provider fence was selected.

## Decision Outcome

### Save the restoration and its cutover together

For a new authorized transition from `SUSPENDED` to `ACTIVE`, advance the same identity's existing credential version exactly once. Save that advancement, principal state, Access revision, required audit and immutable original outcome in one coordinated transaction. An original-result replay or any non-transition never advances the version again. Failed local work rolls back together. After uncertain commit, reconcile the original operation rather than assume rollback or start another transition.

Use the existing identity turn before the required Organization/Project coordination and reread current facts after waiting. Never reset or downgrade a version, reconstruct missing security history, or hold SQL transactions over provider verification or cleanup.

Restoration still requires current `restore-users` authority, the same legitimate identity and security review, confirmed required original cleanup and the applicable current restrictions. Independent recovery blocks remain authoritative. Password reset alone cannot restore a principal. Neither restoration nor replay recreates removed memberships or grants, changes another principal or treats the version as permission.

### Bind browser evidence before final verification

When identity discovery is needed, discover the provider identity, capture its current installation/identity/version binding, then freshly verify the same cookie and exact identity. Only that final verification can establish the bound browser evidence. Never attach a newer version to a verification result obtained earlier.

The discovery and final browser verification share one original absolute provider deadline within the unchanged total authentication budget. Defaults remain five seconds for that shared provider window and ten seconds in total, including local reads. No new allowance starts for the second verification. Required uncertainty fails closed, with no cross-request positive cache or SQL transaction held across provider I/O.

Current authorization compares the captured browser binding with authoritative identity/version facts before protected disclosure, original-result replay or mutation, just as current OAuth binding must be checked. This record selects the logical evidence, not new public wire fields or a parallel authentication framework. [Browser sessions](../../.agents/skills/inframeld-access-models/references/browser-sessions.md#restoration-evidence-cutover) owns the sequence and its limits.

### Preserve pre-admission consent and reject linked blocked humans

Genuinely unadmitted identities retain supported consent, subject to the existing exact identity/installation, version/history and recovery-block checks. Consent neither admits them nor creates grants. For linked humans, initial and final approval observations reject suspension, retirement or incoherent linkage. An initially blocked attempt remains denied even if restored during verification. Missing required linked facts cannot be treated as no local link.

Late Hydra approval retains its originally captured version. Inframeld rejects the older binding after advancement even if Hydra considers the resulting grant active. Do not restamp refresh or a late result with today's version. Existing provider calls, their deadlines and independent cleanup outcomes remain required.

### Explicitly accepted late-session limitation

**A fresh request after restoration may authenticate a Kratos session created late by previously started login work, if Kratos then verifies it as active, unexpired and belonging to the same identity.** This decision does not establish that session's causal generation. It does not invalidate every historical cookie, drain pending login work or prevent all provider issuance.

The fence rejects evidence captured before restoration's cutover. Fresh verification does not prove password persistence or legitimate-person review and cannot substitute for the required original cleanup. Already authorized external effects cannot be recalled. All required current provider checks, confirmed original cleanup and independent recovery restrictions remain mandatory.

## Consequences

The credential fence uses the existing version store for captured browser evidence, neutral currentness observations and linked-human consent guards. It introduces no new epoch registry, executor, token hook or credential inventory. The actual restoration transaction and its identity coordination remain required unfinished work. This supporting component does not establish suspension-specific provider deletion or job cleanup.

Required qualification covers both crossing orders, stale browser contexts, late OAuth issuance, the explicitly tolerated late-created session, replay-once advancement, rollback, cancellation and uncertain commit. It must also cover newer independent recovery blocks, unchanged other principals and rights removed during the incident. Provider and human qualification remain unrun for this decision. Full #188 stays open, with human work tracked in [#318](https://github.com/matejpalenik/inframeld/issues/318).

## Links

- [Restoration and recovery](../../.agents/skills/inframeld-access-models/references/recovery.md#deliberate-restoration-cutover), [browser evidence](../../.agents/skills/inframeld-access-models/references/browser-sessions.md#restoration-evidence-cutover) and [logical records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#restoration-version-transition).
- [Current authorization](../../.agents/skills/inframeld-access-models/references/eligibility-and-current-authority.md#accepted-browser-currentness), [consent](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#linked-human-restoration-checks) and [identity coordination](../../.agents/skills/inframeld-access-models/references/identity-admission-coordination.md#restoration-identity-turn).
- [Kratos session verification](https://github.com/ory/kratos/blob/v26.2.0/session/handler.go#L211), [stored-session deletion](https://github.com/ory/kratos/blob/v26.2.0/persistence/sql/persister_session.go#L325) and [Hydra captured consent metadata](https://github.com/ory/hydra/blob/v26.2.0/flow/consent_types.go#L651) describe the reviewed provider capabilities, not runtime qualification of this contract.
- [ADR-0131](ADR-0131-bind-suspension-cleanup-to-the-original-obligation.md) owns suspension cleanup dispatch, protected continuation and the three independent confirmations needed by this restoration contract. The implementation and selected local pinned Ory journey are now verified in the #188 candidate. Final hosted checks and actual [human acceptance #318](https://github.com/matejpalenik/inframeld/issues/318) are separate.
