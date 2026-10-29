# ADR-0104: Enforce one qualified outbound model path

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Context and Problem Statement

A previously approved hostname can resolve differently, and an SDK can redirect, retry or dispatch nested work outside a checked path. A saved URL alone does not establish safe credential delivery or one paid attempt.

## Considered Options

- Combine a controlled embedded transport with qualified host/network egress enforcement. Selected.
- Use adapter checks alone, with a smaller deployment configuration but weaker protection against an uncontrolled bypass.

## Decision Outcome

All model, metadata, probe, reranker and nested calls use one explicitly qualified path. Validate actual IPv4/IPv6 routes, HTTPS and permitted private destinations. Disable initial-profile automatic redirects, ambient proxy/credential behavior, hidden retries and fallbacks. Unsupported adapters fail closed. Preserve current authority, connection revision, credential, cancellation and spending checks. Known not-sent, known response/failure and uncertain dispatch remain distinct.

The [approved PD-CONTRACTS-01 contract](../../.agents/skills/inframeld-application-contracts/references/decision-gateway-enforcement.md#approved-resolution) owns exact behavior, examples and qualification cases.

## Consequences

Support initially covers only mapped and qualified adapter/features and deployment routes. The existing credential-free local Ollama HTTP exception and private-CA support remain. A timeout cannot authorize another paid attempt. No separate gateway service or general public proxy is introduced.

Backend implementation, native public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-application-contracts/references/decision-gateway-enforcement.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
