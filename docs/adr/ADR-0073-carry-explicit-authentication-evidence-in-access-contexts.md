# ADR-0073: Carry explicit authentication evidence in Access contexts

**Status:** Accepted

**Date:** 2026-10-24

## Context and Problem Statement

Alice's CLI credential needs its original version checked again during authorization. The previous context stored that binding optionally. Missing evidence could therefore look like a browser caller, for whom that version check does not apply. Application authorization scenarios also need an honest representation of their callers.

[ADR-0072](ADR-0072-version-human-cli-credentials-across-account-recovery.md) establishes versioned credentials. This decision refines their request representation without changing authentication, permission or transaction rules.

## Considered Options

- Keep an optional OAuth binding. This leaves absence ambiguous and makes forgotten evidence easy to overlook.
- Require an authentication-method enum and validate the optional binding. This uses fewer record types but requires keeping the enum and field combinations consistent.
- Require one complete evidence record from three concrete alternatives. This is selected. Each alternative carries the data needed for its credential family, without a base class or Protocol hierarchy.

## Decision Outcome

`AccessContextDTO` remains a frozen application transfer record. It requires the local `PrincipalId` and browser-session, human OAuth or application-key evidence. Browser evidence contains the verified provider identity. OAuth evidence retains the existing identity, installation and version binding. Application evidence contains a distinct typed public key ID. No credential secret, mutable account status or permission snapshot is retained.

Context construction rejects absent or unsupported evidence. Authenticators establish the evidence, while dependencies and services pass the context unchanged. A record alone does not authenticate its contents or grant authority.

Current facts readers return the stored principal and OAuth binding/version observations. Both authorizers use the shared application evaluator to check that human evidence matches a human principal and application evidence matches an application principal. A mismatch raises an internal `RuntimeError` before reservation, replay or effects. OAuth evidence retains exact identity-link and version checks through the domain policy. Valid application evidence does not permit human-only work. [Component ownership](../development/application-structure.md#credential-query-and-policy-boundaries) explains this implementation without changing the evidence decision.

Every producer explicitly supplies `PrincipalAccessPolicyInput.credential_is_current`. True for browser/application contexts means the human OAuth generation check is inapplicable. It does not establish the validity of a browser session or application key.

## Consequences

Strict typing catches incomplete constructions, and runtime checks reject unsupported evidence and stored-kind mismatches. Services retain their existing access argument and current authorization boundary. Both the evidence shape and its consumers must be updated deliberately when a further credential family is implemented.

Application-key authentication remains unfinished. Existing authorization tests simulate it with synthetic typed key IDs, without provisioning or verifying keys. This decision creates no endpoint, table, migration or public schema change. Existing recovery coordination and deferred production completion remain unchanged.

## Links

- [Application request chain](../development/application-structure.md#access-context-evidence)
- [Evidence record definitions](../development/data-model.md#authentication-evidence-records)
- [Context construction tests](../../apps/backend/tests/unit/access/application/dtos/test_access_context_dto.py)
- [Stored-kind and workflow tests](../../apps/backend/tests/integration/access/test_authentication_evidence_postgres.py)
