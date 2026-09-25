# ADR-0001: Use one modular backend with clear domain boundaries

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Inframeld has several kinds of business rules: managing documents, preparing indexes, running pipelines, evaluating changes, releasing versions, and controlling access. One developer must be able to maintain them without operating a separate service for each area.

## Considered Options

- One backend with explicit domain ownership and inward-facing application contracts.
- Separate services for each domain, or one undivided application with shared mutable business state.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use a modular backend with Knowledge, Indexing, Pipelines, Evaluation, Releases, and Access as distinct owners. Domain and application rules remain independent of HTTP types, ORM objects, and vendor SDKs. Entry points and infrastructure adapters call application-owned contracts. Keep the API, worker, and restricted processing responsibilities described by the deployment design.

**Example.** Knowledge admits a document. Indexing verifies its prepared search data. Releases changes which ready version serves traffic. An upload handler must not take over all three sets of rules.

## Consequences

- A change has a clear owner while cross-domain work can still use the existing process and database boundaries.
- The team must maintain those boundaries deliberately. Do not add a generic repository, service per domain, command bus, or structural test framework to demonstrate the architecture.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current application structure](../development/application-structure.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0002](ADR-0002-separate-commands-and-queries-without-a-command-bus-framework.md).
