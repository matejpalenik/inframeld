# Private identity-recovery handoff

<a id="private-identity-recovery-handoff"></a>

Alice proves a recovery code, then saves a replacement password. Those are different facts. Access saves the original checklist before allowing recovery to continue, associates the native settings session, then accepts later evidence without trusting a recovery ID from the browser.

**Status:** accepted version 2 design under [ADR-0085](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md). Production callbacks remain unimplemented. The [version 1 schema](../../../../contracts/design/access/recovery-event-v1.schema.json) is retained as a superseded design artifact, not a compatibility path.

## Reading tasks

- [Native evidence](#native-hook-evidence) explains what each hook proves.
- [Private wire contract](#recovery-wire) defines fields, authentication and receipts.
- [Lost evidence and restarted flows](#recover-original-evidence) explains safe reconciliation.
- [Completion](recovery-completion.md) owns Hydra execution, retries and release.

<a id="recovery-callbacks"></a> <a id="private-recovery-admission-and-completion"></a>

## Private recovery admission and completion

Use exactly one `X-Inframeld-Recovery-Key`, checked in constant time against dedicated rotatable service-secret material. Allow bounded current/next overlap during rotation. Product Authorization headers, application keys and browser cookies cannot substitute. Private handlers perform no product authentication or cookie CSRF and remain excluded from public ingress, product OpenAPI and generated clients.

Limit received JSON to **8 KiB (8,192 bytes)**. Reject unknown fields, duplicate keys, multiple JSON values and unsupported versions or event/route combinations. Installation and provider authority come from trusted configuration. Bodies and audit contain no passwords, cookies, tokens, arbitrary provider objects or caller-selected cleanup outcomes. A provider session ID identifies evidence association, not a session credential or instruction to revoke it.

The service key authenticates the sender. Trusted hook placement and the checked association establish what an event means. Neither constructing a typed event nor sending a successful generic webhook proves recovery completion.

<a id="native-hook-evidence"></a>

## Native hook evidence

| Native boundary | Required effect |
| --- | --- |
| Recovery code verified, recovery hook runs | Admit the original flow once, atomically saving its block and advancing the CLI credential version. An anonymous email request cannot do this. |
| Settings-flow creation hook runs | Bind the native settings-flow/session IDs and identity to the already admitted recovery before the flow is handed to the browser. This proves association only. |
| Password is persisted, native `revoke_active_sessions` succeeds, following password-settings webhook runs | Accept Kratos cleanup evidence for that exact association. Preserve the session used to replace the password. This does not confirm Hydra cleanup. |

Configure the creation hook as waited-for and fail settings-flow creation if required association cannot be saved. The password callback must be the post-persistence mode, after native revocation, also waited-for. A failed callback at that later stage does not roll back the password or native cleanup. The recovery webhook's session is not exposed by the pinned template, so do not invent that field there.

For the first association, require a native recovery-created settings context, its exact configured Kratos recovery endpoint, the original recovery flow already admitted for the same identity, and the native settings/session IDs. The route and flow evidence must come from that hook context. A caller's query, body, transient payload or return URL is insufficient. #243 must qualify this distinction, including conflicting query/body identifiers, before production wiring is considered complete.

For a fresh or restarted settings flow, a durable association for the same installation/provider/session/identity can identify the original operation even when the new flow has no native recovery source. Reject attempts to move a bound flow or session to another identity or original operation. Ordinary settings without a trusted recovery association cannot supply recovery proof.

<a id="recovery-wire"></a> <a id="version-1-private-recovery-handoff"></a>

## Version 2 private recovery handoff

The legacy anchor above remains for existing links. These are accepted private design routes, not implemented endpoints:

| POST route | Required `eventType` | Additional required fields |
| --- | --- | --- |
| `/internal/v2/identity-recovery/admit` | `recovery-code-verified` | `recoveryFlowId`, `eventKind` |
| `/internal/v2/identity-recovery/settings` | `settings-flow-associated` | `settingsFlowId`, `sessionId`, `sourceRecoveryFlowId` |
| `/internal/v2/identity-recovery/password-saved` | `password-settings-saved` | `settingsFlowId`, `sessionId`, `sourceRecoveryFlowId` |

Every alternative requires `schemaVersion: 2` and `identityId`. Identity, flow and session IDs are UUID strings. Admission's `eventKind` is `recovery` or `password-reset`, checked against the configured integration. `sourceRecoveryFlowId` is a required nullable field extracted from native context. It is null for a fresh ordinary settings flow. No alternative accepts installation, provider authority, principal, permission, credential version or provider-success assertions.

Resolve both settings events through the stored association. A non-null native source must agree with its original admission. A missing/conflicting recovery admission, changed identity/session binding or password event contradicting its association returns safe 409 without creating a replacement obligation. An ordinary settings event with null source and no recovery association returns 204 with no recovery acknowledgment, admission, version advancement or cleanup. This no-op is not completion evidence.

For a recovery-bound event, return HTTP 202 only after committing its receipt and required state. The safe response fields are `schemaVersion: 2`, the original `operationId`, the checked `eventType` and `recorded: true`. The first trusted password-saved receipt also commits the recoverable job handoff and initial eligibility time. HTTP 202 means durable receipt, not provider success or restored access.

Event identity is configured installation/provider plus event type and its native flow ID: recovery flow for admission, settings flow for association/password evidence. Stored identity, event kind and session/source association must agree on replay. They are checked immutable meaning, not extra key dimensions that permit conflicting second operations. Concurrent repeats return the original recorded acknowledgment. Random delivery IDs do not identify business events.

Use safe existing problem conventions: 401 invalid service credential, 409 conflicting/reordered evidence, 413 oversized body, 422 invalid fields/version/event/route, and 503 unavailable required state or unconfirmed receipt. Do not reflect the key, body or provider error. A released duplicate cannot dispatch provider work, reset a budget or release another block.

<a id="recover-original-evidence"></a>

## Lost evidence and restarted flows

If the commit succeeded but the acknowledgment was lost, repeat the same evidence and recover its receipt. If the password callback was never saved, keep the block. A successful settings status, password timestamp or provider-call timeout cannot manufacture missing post-revocation proof.

Alice may save another password through a flow associated with the same trusted session. If that session is unavailable, she performs a new verified recovery. At its first admission, save explicit links to older unreleased operations for the same installation/provider/subject under [identity coordination](identity-admission-coordination.md). Duplicate admission never expands that set. A recovery admitted afterward is not covered.

Once the newer operation has trusted Kratos proof and both Hydra confirmations, its durable combined proof may satisfy those linked older checklists. Each still undergoes its own binding and current release checks. Preserve original operations, admission metadata, confirmed progress and all run history. Do not reset old budgets, start provider work for an already satisfied obligation or infer coverage from timestamps. An older completion cannot cover a newer recovery. [Logical records](credential-and-recovery-records.md#recovery-delivery-records) own the links and provenance.

The [completion workflow](recovery-completion.md#completion-proof) explains why acknowledged Hydra cleanup and permanent Inframeld rejection of old CLI versions are separate guarantees. Missing Kratos proof prevents Hydra execution even after host authorization. Provider calls remain outside database transactions.

<a id="machine-readable-input-shape"></a>

## Sources and machine-readable shape

[The version 2 design schema](../../../../contracts/design/access/recovery-event-v2.schema.json) expresses the three alternatives. It is not runtime validation. Byte limits, duplicate-key rejection, literal integer tokens, sender trust, native association and database state need separate checks. JSON Schema treats `2.0` as integer-valued, while strict parsing requires the integer token `2`.

The [pinned webhook](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go), [settings handler](https://github.com/ory/kratos/blob/v26.2.0/selfservice/flow/settings/handler.go) and [recovery transition](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/code/strategy_recovery.go) expose the selected stages. Historical v25.4.0 and current v26.2.0 recovery hooks omit session template data. Settings hooks supply it. [Provider observations](recovery-provider-cleanup.md#documented-native-hook-support) distinguish source inspection and earlier tests from unfinished production delivery. [The qualification matrix](decision-recovery-production-completion.md#open-questions-and-required-evidence) assigns the remaining runtime proof to #243–#245.
