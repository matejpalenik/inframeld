# Private identity-recovery handoff

<a id="private-identity-recovery-handoff"></a>

Alice resets her password. A trusted server integration must record the original recovery obligation before old credentials can regain product access. A callback acknowledgment means durable receipt, not that cleanup or release has succeeded.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="recovery-callbacks"></a>

<a id="private-recovery-admission-and-completion"></a>

## Private recovery admission and completion

Private admission/completion callbacks use a dedicated rotatable hook secret. It is neither an application key nor a human credential, and these callbacks are not ordinary product client operations. Allowlist only `schemaVersion`, `flowId`, `identityId`, `eventKind` and `phase` in callback JSON, with a maximum of **8 KiB (8,192 bytes)**. The server validates the configured provider/installation binding. Do not accept caller-selected principals, assignments, sessions to revoke or provider success flags as authority. Callback bodies and audit contain no cookies/tokens.

Derive stable event identity from the installation, flow, event kind and phase, rather than a randomly generated delivery ID. Save the original cleanup obligation and product block before pending cleanup could permit old credentials to regain access. Native Kratos cleanup follows, then trusted ordered completion evidence, independent durable Hydra cleanup and eligible release of this operation's block. A repeated admission recovers its original obligation. A completed duplicate cannot start broad cleanup of later logins. Failed/uncertain outcomes keep the block, and an older operation cannot release a newer one.

The hook secret authenticates the sending service. It does not, by itself, certify a verified reset or completed native cleanup. Those meanings must follow qualified placement and provider evidence. The [version 1 recovery draft](#recovery-wire) supplies private route/header/version/enum declarations and trusted evidence requirements for final review. Qualify ordering, delivery/reconciliation behavior and legitimate-session preservation on the selected pinned OSS releases. Product OpenAPI/generated clients do not gain a recovery bypass.

Recovery/reset separately uses authenticated server-side admission and trusted completion evidence with native Kratos cleanup and durable independent Hydra cleanup. The temporary block must be committed before old credentials could regain product access. Preserve the legitimate recovery session using qualified provider evidence, not a guessed generic webhook session ID. [Recovery](recovery.md#identity-recovery-cleanup) owns the invariant. Must qualify ordering, failures, evidence, deduplication and session preservation on pinned OSS releases before this integration is relied upon.

<a id="recovery-wire"></a>

<a id="version-1-private-recovery-handoff"></a>

## Version 1 private recovery handoff

Expose only on the private service listener, excluded from public ingress/product OpenAPI/generated clients:

| Route | Private operation ID | Input / acknowledgment |
| --- | --- | --- |
| `POST /internal/v1/identity-recovery/admit` | `admitIdentityRecovery` | `IdentityRecoveryEventRequest`, `phase: admit` / 202 `IdentityRecoveryEventResponse` |
| `POST /internal/v1/identity-recovery/complete` | `completeIdentityRecovery` | Same named input, `phase: complete` / 202 same acknowledgment |

Require exactly one `X-Inframeld-Recovery-Key`, verified in constant time against configured dedicated hook-secret material. Product cookie/Authorization credentials cannot substitute. Keep the service secret in protected configuration. Rotate with bounded current/next overlap, then retire the old secret. These adapters do not invoke product human/application authentication or cookie CSRF.

**Design notation, a teaching view of [the existing input schema](../../../../contracts/design/access/recovery-event-v1.schema.json), not production implementation.** UUID values are serialized UUID strings.

```python
from typing import Literal, TypedDict
from uuid import UUID

class IdentityRecoveryEventRequest(TypedDict):
    schemaVersion: Literal[1]
    flowId: UUID       # Original verified flow, shared by both phases
    identityId: UUID   # Verified identity, not a local principal assertion
    eventKind: Literal["recovery", "password-reset"]
    phase: Literal["admit", "complete"]  # Must match the private route
```

The received body is at most 8 KiB. Reject unknown and duplicate fields through the required strict parsing boundary. The annotations do not enforce those checks. The phase must match the route. Configured provider/installation binding is server-owned. `flowId` identifies the original verified recovery/reset flow for both phases. An unrelated later settings flow cannot replace it. The trusted integration must retain/resolve any recovery-to-settings association needed by the chosen provider sequence. Routine profile edits, anonymous email requests and browser redirects are not these events.

The documented acknowledgment has this design shape. The input schema does not define this response.

```python
class IdentityRecoveryEventResponse(TypedDict):
    operationId: str
    eventKind: Literal["recovery", "password-reset"]
    phase: Literal["admit", "complete"]
    recorded: Literal[True]  # Durable receipt only
```

HTTP 202 acknowledges durable receipt, not provider cleanup success or product access. Use the existing safe problems for 401 invalid service credential, 409 conflicting/reordered evidence, 413 oversize, 422 invalid envelope/version/phase and 503 unconfirmed required dependency. Identity/flow mismatches return a safe 409 without target details. No callback error reflects the hook secret, body, cookies or provider text.

Derive the business event key from configured installation/provider, original flow, event kind and phase. The two phases bind to one original cleanup operation and one verified identity. A reused flow with a different identity/kind conflicts. A completion without its durable admission cannot create an obligation or clear a block: reject 409 and require reconciliation of the original admission. Concurrent repeats recover the one recorded acknowledgment. An already-completed duplicate returns that result without another native/broad Hydra revocation or a block release. Record event identity/evidence safely, not random delivery IDs as business identity and not proof credentials.

Access owns local blocking, the original durable obligation, independent provider outcomes and eligible release. The trusted Kratos integration owns verified reset evidence, ordered native cleanup and legitimate-session preservation. Its service-authenticated callback alone does not prove those outcomes. Admit must durably block before the pending cleanup interval can authorize product access. Confirmed native Kratos cleanup must precede trusted complete evidence. The worker then reconciles that subject's CLI grants and Hydra remembered logins independently. Under [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md), unfinished retries and already-dispatched calls may invalidate newer CLI credentials. Completed events initiate no new cleanup. Kratos's legitimate recovery session remains protected. Uncertain outcomes remain blocked, suspended users still need deliberate Restore users, and an older completion cannot release a newer block.

**Production qualification gate:** demonstrate on selected pinned OSS releases that callback placement follows verified recovery/reset, admission failure prevents an unblocked reset, native cleanup preserves the legitimate new session, completion really follows confirmed native cleanup, changed recovery/settings flow IDs retain their original binding, and a lost callback/provider response can be reconciled with bounded subject-scoped bulk cleanup and completed-event deduplication. Later CLI credentials may be invalidated by an unfinished retry or already-dispatched call. Qualify coordination with token issuance, including authorization-code exchanges and refresh requests already underway, before treating Hydra cleanup as complete. Bound retries and persist unresolved obligations. Exhausted reconciliation stays blocked and visible to host operations. Do not publish a guessed hook configuration or mark cleanup confirmed just because the generic webhook returned success. The inspected [Kratos v25.4.0 recovery webhook](https://raw.githubusercontent.com/ory/kratos/v25.4.0/selfservice/hook/web_hook.go) supplies flow/identity but does not add the recovery session to that hook's template context. This source observation is not runtime qualification. Report an unsupported chosen placement as a contract conflict, rather than silently weakening the required block/evidence boundary.

The original v25.4.0 source observation above remains historical evidence. The current [v26.2.0 recovery hook](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go) still omits the recovery session, while both settings hooks now expose their current session. [Upgrade qualification](authorization.md) records the changed observation and preserved recovery assertions. A session ID in a pre-save callback is not confirmation of password persistence or native cleanup.

<a id="machine-readable-input-shape"></a>

## Machine-readable input shape

[The design-only JSON Schema](../../../../contracts/design/access/recovery-event-v1.schema.json) expresses the documented envelope. It is not a runtime model or proof of authorization, trusted event ordering or provider completion. PD-ACCESS-03 and PD-ACCESS-04 retain their existing pending scope.

A structural validator cannot establish received-byte limits, reject duplicate JSON keys after decoding, verify a credential or enforce database state. JSON Schema treats `1` and `1.0` as the same integer value. Strict token parsing remains a separate requirement. Future implementation must reconcile or supersede this design schema with its runtime-owned definition.
