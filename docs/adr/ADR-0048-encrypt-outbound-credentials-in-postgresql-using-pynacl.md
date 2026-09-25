# ADR-0048: Encrypt outbound credentials in PostgreSQL using PyNaCl

Status: Accepted

**Date:** 2026-09-19

## Context and Problem Statement

A saved provider key must survive restart and be recoverable for an authorized outbound call. A hash cannot supply its plaintext later, while a required external secret service would add operational scope.

## Considered Options

- Application-managed authenticated ciphertext in PostgreSQL using PyNaCl Aead.
- OpenBao KV v2.
- PostgreSQL encryption using cryptography AESGCM.
- Deployment-managed secret files as the only provider-key mechanism.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Store application-entered outbound credentials as authenticated ciphertext in PostgreSQL using the selected PyNaCl adapter. Bind ciphertext to its documented organization, project, connection, and revision. Supply a separate persistent deployment root key outside the database. Resolve plaintext only for authorized, approved-destination use and keep management responses metadata-only.

**Example.** Restoring ciphertext without the matching root key must make the connection unavailable. The application must not select a different key, provider, or plaintext fallback.

## Consequences

- Provider credentials persist within the existing deployment while a copied database alone lacks the separately supplied decryption key.
- Key persistence, backup, controlled replacement, safe retries, and fail-closed behavior require qualification. This boundary does not protect plaintext from the trusted host operator or a process already authorized to decrypt it.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current model connections](../development/model-connections.md).
- [Current data model](../development/data-model.md).
- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
