# ADR-0002: Separate commands and queries without a command-bus framework

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Changing application state and reading a useful view have different needs. Loading large aggregates merely to produce a list adds work without protecting a business rule.

## Considered Options

- Lightweight separate command and query paths.
- A generic command bus, event-sourced engine, or one repository abstraction for every object.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use explicit application use cases for changes and direct scoped read models for queries. Domain objects protect meaningful rules. Read projections may join the needed data without taking over another domain’s writes. Keep the design lightweight and avoid a framework introduced only to demonstrate CQRS.

**Example.** A deployment list can read a bounded projection. It need not load every pipeline version and receipt into a deployment object.

## Consequences

- Read paths can remain efficient and changes retain clear transaction and domain ownership.
- Developers must choose real consistency boundaries and preserve scope in read queries. This does not authorize uncontrolled cross-domain writes.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current application structure](../development/application-structure.md).
- Related decisions: [ADR-0001](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
