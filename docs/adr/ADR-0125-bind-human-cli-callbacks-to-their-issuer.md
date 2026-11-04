# ADR-0125: Bind human CLI callbacks to their issuer

**Status:** Accepted. Narrowly supersedes [ADR-0053](ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md) and its linked registration contract only for callback-path binding and response association. Its human identity, first-party client, consent, credential and host-authority choices remain selected.

**Date:** 2026-10-30

## Context and Problem Statement

Alice uses dev and production through one CLI. A callback from one issuer must not cause code exchange against another. The existing shared `/oauth/callback` path and state alone do not establish the accepted multi-issuer defense.

The scoped probe of digest-pinned Hydra v26.2.0 reported neither RFC 9207 advertisement nor `iss` on success/error callbacks. Inspection found no supported native issuer-response switch in that release. The probe used administrative test approval and exchanged no tokens. It does not establish operator proof acquisition or production security qualification.

The developer explicitly approved the reviewed concrete callback design and its listed documentation changes on this date. Acceptance does not establish implementation or qualification.

## Considered Options

- Prefer maintained native RFC 9207 support when a supported configuration or suitable maintained release is available and qualified on both outcomes.
- Select the standards-documented distinct redirect URI per issuer under a restricted first-party deployment profile.
- Wait for upstream support and keep the dependent acquisition journey blocked.
- Restrict the product to a genuinely single-issuer profile, which conflicts with the accepted multi-installation journey. One pending attempt is not such a restriction.

## Decision Outcome

Select `/oauth/callback/<digest>`, using the complete lowercase hexadecimal SHA-256 of the exact trusted issuer string's UTF-8 bytes. Preserve spelling, case, path and trailing slash, with no normalization, truncation or caller-chosen suffix. Reject conflicting mappings. The digest is not a secret or proof.

Private provisioning registers exactly `http://127.0.0.1/oauth/callback/<digest>` without a port. Only the ephemeral port varies at authorization. Preserve literal loopback, public `inframeld-cli`, code-only responses, S256 PKCE and existing scopes/audience. Exchange uses the identical complete redirect URI captured for that attempt.

Freeze installation/target, exact API/audience/issuer/client, validated endpoints/transport, account intent, complete redirect URI and fresh state/nonce/PKCE before opening the browser. Before code exchange or OAuth-error classification, validate the actual listener address/port, exact Host/path and pending state. Reject repeated singleton parameters, contradictory payloads, replay and cross-attempt responses. Do not follow `error_uri` or reflect uncontrolled descriptions.

Advertised RFC 9207 requires one exact matching `iss` on success and error. The selected local policy also checks any unadvertised-but-present `iss`. Absence is allowed only with the qualified distinct-path defense. Keep maintained-library ID-token validation and opaque access-token handling. Host execution, independent current recipient verification, admission and product authority remain separate.

This defense requires trusted private administration, no attacker-accessible registration or alternative approval path, and no registration of another issuer's callback on the honest server. Provisioning preserves unrelated clients and cannot certify those conditions. Installations permitting attacker-controlled client registration are outside the qualified profile.

Patch the existing client in place, preserving independent login chains and consent. Cancel/restart pending attempts without rewriting their redirect URI or retaining a legacy fallback. Registration change and the one-minute code lifetime do not prove outstanding flows are cancelled. Actual issuer/configuration changes retain saved-login invalidation rules.

[PD-ACCESS-07](../../.agents/skills/inframeld-access-models/references/decision-human-cli-issuer-binding.md) owns detailed constraints and qualification. The maintained proof capability uses the single selected `apps/cli/src/auth/` allocation. No new public command syntax, authentication framework or issuer runtime is delivered by this record.

## Consequences

Distinct paths provide a documented defense for the supported deployment profile while native issuer identification remains unavailable. Exact-byte hashing must agree across the provisioner and CLI. Cutover needs explicit pending-attempt handling and real provider evidence for old codes, consent and credential-chain preservation.

The production provisioner now receives the exact trusted issuer from the existing setup command and registers only its derived callback path. Managed changes use in-place patching and bounded readback, without deliberately resetting consent or revoking independent chains. The maintained pinned-provider run passed legacy cutover and independent-chain preservation. Original codes retained their URI binding, while unchanged legacy consent resumed to invalid-current-registration without a code. These are pin-specific compatibility observations under PD-ACCESS-07, not complete acquisition qualification. The shared Rust repair-only consumer now implements callback association, maintained-library token validation, generated current-session verification and protected-stdin handoff. The [verification report](../development/reports/recipient-proof-verification.md) distinguishes controlled checks and selected native-driver coverage from remaining operator, system-browser, additional-platform and deployment qualification. The qualified operator acquisition gap stays open. No proxy-invented issuer parameter, private protocol fork, post-exchange substitute, admission shortcut or broader repair authority is introduced.

## Links

- [PD-ACCESS-07](../../.agents/skills/inframeld-access-models/references/decision-human-cli-issuer-binding.md), [registration](../../.agents/skills/inframeld-access-models/references/human-cli-login.md#cli-client-registration), [attempt lifecycle](../../.agents/skills/inframeld-access-models/references/human-cli-credential-lifecycle.md#cli-login-transaction) and [host proof](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#maintenance-wire).
- [ADR-0053](ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md) and [ADR-0098](ADR-0098-publish-bounded-first-party-discovery.md) retain their other accepted choices.
- [RFC 9700 §4.4.2.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.4.2.2), [RFC 8252 §7.3](https://www.rfc-editor.org/rfc/rfc8252.html#section-7.3) and [RFC 9207 §2.4](https://www.rfc-editor.org/rfc/rfc9207.html#section-2.4).
