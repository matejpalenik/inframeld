# PD-ACCESS-05: Implement and qualify the selected provider-secret lifecycle

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation detail and security qualification.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice saves a provider key, Bob replaces it concurrently, and a worker is about to send a model request. Later the operator restores a backup with the wrong encryption-key file. The implementation must preserve the selected winner, destination binding and safe failure without leaking or silently replacing secrets.

Encryption, key separation and permissions are accepted. The missing work is the concrete management/storage integration and its end-to-end evidence. This entry must not turn the absence of that implementation into an invitation to choose a different cipher, vault or key hierarchy.

## Accepted context and evidence

Preserve application-managed PyNaCl authenticated ciphertext, resource binding, key IDs, expected revisions, secret-safe errors and no secret replay. The root key is generated once, protected outside the database and mounted only into the API/worker. Missing or wrong key material fails visibly and never generates a replacement.

Provider-secret replacement differs from deployment-root-key replacement. Future controlled root-key re-encryption retains old keys until verified and is not a new v1 online key-management feature. Current account/grant checks remain separate from decryption. The reviewed guide is design evidence, not proof of an implemented credential store.

## Alternatives and trade-offs

1. **Integrate protected management and dispatch in one vertical slice.** Exercise save/replace/remove, current dispatch and restore against the real selected storage. This exposes boundary mistakes early, but needs more assembled dependencies before qualification.
2. **Implement the same contract in staged layers.** Start with serialization/encryption and concurrent storage behavior, then qualify gateway and restore integration before release. This gives faster focused feedback, but isolated tests cannot certify the complete secret boundary.

## Non-binding recommendation

**Proposal only.** Prefer staged implementation followed by mandatory assembled qualification. The alternatives describe delivery/evidence order, not alternative security policies. Keep the selected cryptography and root-key lifecycle, and resolve only concrete interface details needed by the first consumer.

## Decision trigger and stopping boundary

When implementing protected provider-credential management, storage or deployment-key integration, and before claiming the complete secret boundary is qualified.

Only an unresolved interface choice needs design approval before dependent code. Missing integration evidence blocks production claims, not authorized tests of the accepted design.

## Architectural impact and dependencies

Access credential-management authority, credential-store adapter, ModelGateway resolution, bootstrap mounts, backup/restore procedures and secret-lifecycle diagrams. No arbitrary-header API or online root-key management UI follows.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01: Enforce model policy on the actual outbound path](../../inframeld-application-contracts/references/decision-gateway-enforcement.md). When decrypted secrets reach the outbound transport.
- [PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment](../../inframeld-architecture/references/decision-availability-backup-and-restore.md). When qualifying backup/restore of keys and encrypted records.

## Open questions and required evidence

- Which typed metadata/result and safe error contract does the first management operation expose?
- How are ciphertext, revision, audit and original retry outcome saved together?
- Which assembled tests prove swap/corruption/wrong-key failure and secret-safe logs?
- How is restore evidence tied to the exact root-key and configuration set?

## Sources and finalization

- [Credential management](provider-credential-storage.md#credentials).
- [Persistent root key](provider-credential-storage.md#root-key).
- [Encryption decision](../../../../docs/adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md).
- [Connection dispatch](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
