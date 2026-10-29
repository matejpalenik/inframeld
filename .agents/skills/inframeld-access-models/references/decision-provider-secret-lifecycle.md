# PD-ACCESS-05: Implement and qualify the selected provider-secret lifecycle

**Status:** ACCEPTED on 2026-10-29 in [ADR-0103](../../../../docs/adr/ADR-0103-save-provider-secrets-through-revision-checked-atomic-management.md). Implementation and qualification remain pending.

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation detail and security qualification.

The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice saves a provider key, Bob replaces it concurrently, and a worker is about to send a model request. Later the operator restores a backup with the wrong encryption-key file. The implementation must preserve the selected winner, destination binding and safe failure without leaking or silently replacing secrets.

Encryption, key separation and permissions are accepted. The missing work is the concrete management/storage integration and its end-to-end evidence. This entry must not turn the absence of that implementation into an invitation to choose a different cipher, vault or key hierarchy.

## Accepted context and evidence

Preserve application-managed PyNaCl authenticated ciphertext, resource binding, key IDs, expected revisions, secret-safe errors and no secret replay. The root key is generated once, protected outside the database and mounted only into the API/worker. Missing or wrong key material fails visibly and never generates a replacement.

Provider-secret replacement differs from deployment-root-key replacement. Future controlled root-key re-encryption retains old keys until verified and is not a new v1 online key-management feature. Current account/grant checks remain separate from decryption. The reviewed guide is design evidence, not proof of an implemented credential store.

## Alternatives and trade-offs

These preserve the options considered before approval. The approved resolution below owns the selected contract.

1. **Integrate protected management and dispatch in one vertical slice.** Exercise save/replace/remove, current dispatch and restore against the real selected storage. This exposes boundary mistakes early, but needs more assembled dependencies before qualification.
2. **Implement the same contract in staged layers.** Start with serialization/encryption and concurrent storage behavior, then qualify gateway and restore integration before release. This gives faster focused feedback, but isolated tests cannot certify the complete secret boundary.

## Approved resolution

Use staged implementation with mandatory assembled qualification before release. Management receives the exact authorized connection/credential identity, expected current revision, request identity and the new protected secret when relevant. Plaintext is transient input. Authorized operations are save, replace, remove and safe metadata inspection, with no provider call implied by saving a credential.

Preserve PyNaCl Aead, XChaCha20-Poly1305, the separate 32-byte deployment key and library-generated 24-byte nonce. Store the returned encrypted message, format, algorithm and key identifiers. Authenticate the existing purpose/version, organization, Project, connection, credential and credential-revision binding as unambiguously encoded associated data reconstructed from trusted records.

Check current authority and the expected revision in the owning transaction. Save ciphertext/removal, the new credential revision, safe original retry outcome and required audit together. Concurrent replacements cannot silently overwrite one another. Use the established keyed request fingerprint so a retry with changed secret input is not mistaken for the original command.

Return a typed safe result with the affected identities, resulting revision and whether a credential is present or removed. Distinguish a confirmed mutation from a recovered original outcome. Do not return secret bytes, ciphertext or verifier material. A lost acknowledgment recovers only the original safe metadata, not another change or a plaintext echo.

Keep invalid input, denied authority, stale revision, missing required credential, unavailable key/store and unusable encrypted material as safe distinguishable application outcomes where the existing public disclosure contract permits. Do not expose provider bodies, submitted values or cryptographic internals in public errors. No new HTTP status or endpoint name is selected by this packet.

At each bounded authorized dispatch, resolve the permitted current credential and decrypt inside the adapter for that call. Keep no long-lived plaintext cache. Credential replacement alone does not change the connection's access revision or the model selected by an existing operation. Removing a required credential blocks later sends, while already sent requests remain in flight.

Missing/wrong deployment keys and damaged/swapped ciphertext fail closed. Never generate a replacement root key automatically or fall back to an old provider secret. Preserve protected backup key material separately from the database and bind restore qualification to the exact database/configuration/key set. Keep online root-key rotation out of v1, as already selected. Resource binding does not claim to detect a complete rollback of the entire trusted database record.

## Decision trigger and stopping boundary

Apply this accepted contract when the implementation reaches its original trigger. Concrete method names and physical representations remain ordinary implementation choices. Qualification limits support and release claims, not authorized evidence gathering. Discuss a new policy choice only if it would change this approved contract.

## Architectural impact and dependencies

Access credential-management authority, credential-store adapter, ModelGateway resolution, bootstrap mounts, backup/restore procedures and secret-lifecycle diagrams. No arbitrary-header API or online root-key management UI follows.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01: Enforce model policy on the actual outbound path](../../inframeld-application-contracts/references/decision-gateway-enforcement.md). When decrypted secrets reach the outbound transport.
- [PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment](../../inframeld-architecture/references/decision-availability-backup-and-restore.md). When qualifying backup/restore of keys and encrypted records.

## Implementation and required evidence

These are required cases and evidence, not recorded passing tests.

Concurrent replace/remove, lost acknowledgment and changed retry input, resource swap/tampering, wrong or missing root key, secret-safe logs/errors, current-secret dispatch, removal after admission and coherent restore. Use private fixtures and controlled providers, without an unauthorized paid probe.

## Sources and finalization

- [Credential management](provider-credential-storage.md#credentials).
- [Persistent root key](provider-credential-storage.md#root-key).
- [Encryption decision](../../../../docs/adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md).
- [Connection dispatch](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch).

[ADR-0103](../../../../docs/adr/ADR-0103-save-provider-secrets-through-revision-checked-atomic-management.md) records the approval and rationale. Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim successful qualification.
