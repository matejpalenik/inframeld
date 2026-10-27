# Private identity-recovery handoff

<a id="private-identity-recovery-handoff"></a>

Alice proves a recovery code, then saves a replacement password. Those are different facts. Access saves the original checklist before allowing recovery to continue, associates the native settings session, then accepts later evidence without trusting a recovery ID from the browser.

**Status:** accepted version 2 design under [ADR-0085](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md). The private callback process and native delivery are implemented. Hydra execution, proof propagation and checked block release are implemented. Protected host continuation is implemented under the [maintenance contract](host-maintenance.md#recovery-cleanup-continuation). The [version 1 schema](../../../../contracts/design/access/recovery-event-v1.schema.json) is retained as a superseded design artifact, not a compatibility path.

## Reading tasks

- [Native evidence](#native-hook-evidence) explains what each hook proves.
- [Private wire contract](#recovery-wire) defines fields, authentication and receipts.
- [Lost evidence and restarted flows](#recover-original-evidence) explains safe reconciliation.
- [Completion](recovery-completion.md) owns Hydra execution, retries and release.

<a id="recovery-callbacks"></a> <a id="private-recovery-admission-and-completion"></a>

## Private recovery admission and completion

Use exactly one `X-Inframeld-Recovery-Key`, checked in constant time against dedicated rotatable service-secret material. Allow one retiring key until its explicit acceptance deadline. Load both keys from protected files and restart to apply rotation. Product Authorization headers, application keys and browser cookies cannot substitute. Private handlers perform no product authentication or cookie CSRF and remain excluded from public ingress, product OpenAPI and generated clients.

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

For the first association, require a native recovery-created settings context, its exact configured Kratos recovery endpoint, the original recovery flow already admitted for the same identity, and the native settings/session IDs. The route and flow evidence must come from that hook context. A caller's query, body, transient payload or return URL is insufficient. The native tests qualify this distinction, including a conflicting body flow ID that cannot replace the native query-selected recovery.

For the exact native recovery endpoint, both templates require one literal `flow` parameter with an unescaped, standard hyphenated UUID. Query parameter names must be plain ASCII letters, digits or the unreserved `-._~` characters. Reject encoded names, duplicate selectors, missing/empty or malformed selectors and malformed query fields with a constant template error before sending a callback. Never reinterpret an invalid recovery source as ordinary settings. Unrelated values such as `return_to` may remain URL-encoded. These rules deliberately accept a narrower, unambiguous form than Kratos's general query parser.

A rejected source may follow already committed admission and provider code acceptance. Preserve that original operation, credential-version advancement and block without recording an association, password proof or cleanup job. A fresh verified recovery remains the recovery path. [Native source regressions](../../../../apps/backend/tests/integration/kratos/test_native_recovery_notifications.py) exercise two recoveries for Alice, encoded/duplicate selectors and the accepted encoded return URL.

For a fresh or restarted settings flow, a durable association for the same installation/provider/session/identity can identify the original operation even when the new flow has no native recovery source. Reject attempts to move a bound flow or session to another identity or original operation. Ordinary settings without a trusted recovery association cannot supply recovery proof.

<a id="recovery-wire"></a> <a id="version-1-private-recovery-handoff"></a>

## Version 2 private recovery handoff

The legacy anchor above remains for existing links. These routes are implemented only in the private callback application:

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

[The version 2 design schema](../../../../contracts/design/access/recovery-event-v2.schema.json) expresses the three alternatives. It is not runtime validation. The runtime mapper and private boundary separately enforce byte limits, duplicate-key rejection, literal integer tokens, sender trust, native association and database state. JSON Schema treats `2.0` as integer-valued, while strict parsing requires the integer token `2`.

The [pinned webhook](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go), [settings handler](https://github.com/ory/kratos/blob/v26.2.0/selfservice/flow/settings/handler.go) and [recovery transition](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/code/strategy_recovery.go) expose the selected stages. Historical v25.4.0 and current v26.2.0 recovery hooks omit session template data. Settings hooks supply it. [Provider observations](recovery-provider-cleanup.md#documented-native-hook-support) distinguish source inspection and earlier probes from the native delivery tests below. [The qualification matrix](decision-recovery-production-completion.md#open-questions-and-required-evidence) assigns the required behavioral proof to #243–#245.

<a id="implemented-private-delivery"></a>

## Implemented private delivery

[IdentityRecoveryNotificationService](../../../../apps/backend/src/inframeld_backend/access/application/services/identity_recovery_notification_service.py) owns each short transaction. Admission reuses the existing writer, then saves its receipt. For either settings notification, the [association facts reader](../../../../apps/backend/src/inframeld_backend/access/application/protocols/identity_recovery_association_facts_reader.py) acquires identity then organization coordination and reads source, session and settings candidates together. It returns observations, including a missing version or conflicting binding. Named application methods select and check the original admission. The evidence writer persists that checked association, preserving immutable bindings and event meaning without choosing the recovery.

Password evidence then loads `IdentityRecovery`, records its Kratos-confirmation transition and saves the aggregate. Receipt persistence returns the original database timestamp. The service uses that time to construct [IdentityRecoveryCleanupRunBudget](../../../../apps/backend/src/inframeld_backend/access/application/value_objects/identity_recovery_cleanup_run_budget.py) and explicitly ensures the initial handoff when cleanup remains unfinished. The application value derives twelve attempts and a one-hour deadline. Persistence stores those supplied limits once. Replays and later settings events preserve the original job, run and progress. The budget grants no cleanup authority. Neither this service nor its private app calls Hydra or releases access.

[The private bootstrap](../../../../apps/backend/src/inframeld_backend/bootstrap/recovery_application_factory.py) uses one clean request-local session and focused configuration. Its ten-second request budget includes body receipt. The five-second database stage includes transaction exit. Cancellation or an unavailable acknowledgment does not prove that commit failed. Repeat the original evidence to recover its receipt.

The settings and password-saved Jsonnet templates intentionally repeat their source guards. Kratos's [sandbox forbids imports](https://github.com/ory/kratos/blob/v26.2.0/oryx/jsonnetsecure/jsonnet.go). Keep both self-contained and qualify both hook stages when changing those guards. Their source observations can differ as Kratos creates or restarts a settings flow. A bound session carries the original association when the native source is absent.

[Native qualification](../../../../apps/backend/tests/integration/kratos/test_native_recovery_notifications.py) proves that anonymous requests create nothing, code verification alone leaves cleanup pending, settings inherit the original session association, and password evidence follows persistence and native revocation. Kratos also creates another settings flow after successful password settings. All associated flows retain the same original operation. Rejected admission persistence redirects to Kratos's error UI without a recovery session. Ordinary settings and conflicting body identifiers cannot manufacture another association.

[Persistence tests](../../../../apps/backend/tests/integration/access/test_identity_recovery_notifications_postgres.py) cover replay, retained budgets, concurrent evidence, cancellation and rollback. The private process is selected by [ADR-0086](../../../../docs/adr/ADR-0086-serve-recovery-notifications-through-a-private-backend-process.md). Development activation remains explicit. Run callbacks and the dedicated recovery worker together after applying the supported migration. A receipt still supplies no release authority. The [completion workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) owns execution, newer-proof propagation and checked release. The separate [host-maintenance command](host-maintenance.md#recovery-cleanup-continuation) authorizes additional bounded runs.
