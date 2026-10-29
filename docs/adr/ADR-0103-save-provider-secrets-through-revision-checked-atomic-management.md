# ADR-0103: Save provider secrets through revision-checked atomic management

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Context and Problem Statement

Alice and Bob replace the same provider credential concurrently. A lost acknowledgment must not repeat a replacement, disclose plaintext or let a stale change overwrite the winner. Encryption and the deployment key are already selected.

## Considered Options

- Implement the same security contract in staged layers, then require assembled qualification. Selected.
- Integrate management, dispatch and restore as one vertical slice before focused qualification.

## Decision Outcome

Use authorized, expected-revision management. Commit ciphertext or removal, its credential revision, safe original retry outcome and required audit together. Preserve the selected PyNaCl Aead and trusted associated-data resource binding. Replay safe metadata only. Resolve current credentials per call, and fail closed for missing/wrong root keys or unusable encrypted material. Never generate a replacement root key automatically or silently reuse an older provider secret.

The [approved PD-ACCESS-05 contract](../../.agents/skills/inframeld-access-models/references/decision-provider-secret-lifecycle.md#approved-resolution) owns exact behavior, examples and qualification cases.

## Consequences

Staging gives earlier feedback without certifying the complete boundary. Operators must retain protected key material with the matching restore set. Ciphertext binding does not detect rollback of an entire trusted database record. Online root-key management remains outside v1.

Backend implementation, native public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-access-models/references/decision-provider-secret-lifecycle.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
