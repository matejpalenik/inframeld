# ADR-0076: Separate index preparation, retrieval and retirement

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Alice's query needs permitted retrieval, while a worker prepares B2 and later retires unused numerical data. Those operations have different lifetimes and I/O authority. The accepted Indexing protocols already fix readiness, frozen writes and cleanup safety, but the application capability split was open.

## Considered Options

- One broad index-management interface exposes preparation, querying and cleanup. It reduces initial wiring but mixes API reads with worker mutation responsibilities.
- Focused preparation/readiness, retrieval and numerical retirement capabilities exchange explicit verified bindings. This makes their obligations visible but requires shared binding/result and resource-lifetime contracts. This is selected.

## Decision Outcome

Indexing separates preparation/readiness, permission-filtered retrieval and numerical retirement/cleanup into focused application capabilities. Preparation and retirement keep vector mutations behind the supported singleton worker writer. Retrieval gives API/query callers the read capability they need.

The capabilities exchange explicit identities and typed bindings for the exact corpus, profiles, generations and layout. Existing PostgreSQL authority, private artifact storage, Chroma selection, complete verification, frozen-byte retries, current health and retention gates remain authoritative. All remote embedding work uses ModelGateway. Shared jobs and transactions support these operations without a generic workflow engine.

## Consequences

Specify trusted inputs, complete binding/result contracts, readiness versus current-health obligations, unavailable outcomes and cleanup/retention coordination before coding the ports. These are logical capabilities, not a class, repository or process per box. Exact backend, security, resource and concurrency qualification remains required. A numerical reuse key cannot authorize redispatch of an uncertain paid request.

This records accepted target architecture. Implementation and qualification remain unfinished. Existing product decisions remain authoritative, and no earlier ADR is superseded.

## Links

- [Current owning guide and remaining design](../development/indexing.md#indexing-capability-boundaries).
- [Logical records](../development/data-model.md#indexing).
- [Module architecture](../../.agents/skills/inframeld-indexing/references/architecture.md).
- [Application/component conventions](../development/application-structure.md#component-conventions) and [modular-backend decision](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
