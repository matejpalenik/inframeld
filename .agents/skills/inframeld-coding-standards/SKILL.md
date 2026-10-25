---
name: inframeld-coding-standards
description: Guides Inframeld repository code planning, suggestions, additions, changes and reviews, including tests and code snippets in any language. Teaches backend Python conventions and routes other languages to existing guidance. Behavior-only tracing and documentation-only work do not require it merely because source is inspected.
---

# Inframeld coding standards

Help a developer choose and review components that are easy to find and hard to misuse. Load this skill before any Inframeld repository code planning, suggestions, additions, changes, refactoring or reviews, including tests and code snippets. The worked examples teach backend Python. For another language, follow its existing directory and language guidance, including [web instructions](../../../apps/web/AGENTS.md), without applying Python roles or declarations. New Rust and TypeScript standards remain deferred.

This skill owns coding conventions. The domain skill explains the product rule, and Application Contracts explains orchestration and execution boundaries.

Explaining an existing workflow, tracing a request or doing documentation-only work does not require this skill solely because source is inspected. Load it before the task starts suggesting code changes or evaluating code quality, structure, declarations or convention conformance.

## Working model

Alice adds an HTTP operation that changes a project grant. Its mapper converts validated input into typed values and a Command. An instantiated service coordinates current authorization and persistence through injected protocols. The aggregate owns the state change. A mapper must not quietly become an authorizer or database writer.

The same separation applies to smaller choices. A `PrincipalId` protects identity meaning even though its stored value is a UUID. `ValueValidation` groups shared primitive checks behind qualified static calls. Neither type proves that Alice exists or has permission.

## Essential conventions

- Choose domain, layer and component role before choosing a file or class name. Use one primary public production type per defining module and import it directly.
- Default reusable pure production conversion and validation utilities to cohesive named classes with `@staticmethod` methods. Existing mapper and policy roles require static methods. Keep small private helpers, fixtures and framework-required callables as functions.
- Keep services instantiated with injected collaborators. Keep state transitions and value-specific invariants on their owning entities or value objects. For an aggregate change, load the aggregate in checked scope, invoke its business behavior and save through its specific repository inside the owning workflow safeguards. Avoid miscellaneous `Utils` classes and mutable utility-class state.
- Use dedicated value types when identity, invariants, secrecy or accidental mixing matter. Preserve enums/literals for closed vocabularies and documented primitive/serialization exceptions. Do not wrap every primitive for symmetry.
- Use standard frozen, slotted dataclasses for immutable records. Preserve runtime ID distinctions, secret-safe representations and the narrow accepted record-interface exceptions.
- Protocol implementations explicitly inherit their contract, implement required abstract members and mark overrides. Preserve strict Pyright. Use typed SQLAlchemy mappings/expressions under the exact persistence exception rules.
- Verify behavior through the repository's scaffold-first TDD sequence. Review organization manually rather than adding structural enforcement tests.

These conventions apply to backend Python suggestions and reviews as well as authorized implementation. They do not grant permission to write files. Existing code is not automatically migrated by a documentation change.

## Explain, suggest or review

1. Select the language and applicable directory guidance. For domain-specific backend component design, code generation or structural review, read the owning domain skill's architecture reference and relevant workflow. Shared components use [Application Contracts’ shared component view](../inframeld-application-contracts/references/components-and-services.md), with its transaction/job or gateway reference when applicable. Read domain context when product behaviour matters. Use accepted architecture and inspected implementation as their status permits. A proposal awaits a decision before code depends on it.
2. Select the component's role, destination, declaration and behavioral contract. For backend Python, read component roles. Load only the references needed for that choice. Their worked examples explain the situation, decision, code, flow and failures. Do not copy every grant collaborator into a workflow that does not need it.
3. Follow values from the external boundary through typed application contracts and back. Check current authority and resource ownership separately from type correctness.
4. Show complete contextual examples with exact paths, imports and placement. Distinguish inspected code from illustrative suggestions and future design.
5. Check failure behavior, typing and meaningful tests. Report the convention, its reason and its effect when reviewing a violation. Do not turn legitimate exceptions into blanket bans.

## Read as needed

- Before planning, suggesting, writing, refactoring or reviewing a backend component, read [Component roles and imports](references/component-roles-and-imports.md).
- Before suggesting or reviewing a backend service or complete write, read [Services and use cases](references/services-and-use-cases.md) for the complete grant example and its workflow variations.
- For backend aggregates or repositories, read [Aggregates and repositories](references/aggregates-and-repositories.md) for domain behavior, scoped loading, supported saves and lifetime.
- For reusable helpers, policies or mappers, read [Static utilities and mappers](references/static-utilities-and-mappers.md).
- For IDs, secrets, value objects, Commands, Queries or other records, read [Values and records](references/values-and-records.md).
- For protocols, adapters, fakes or database access, read [Protocols and persistence](references/protocols-and-persistence.md).
- For tests, scaffolding, docstrings or test-support records, read [Testing and documentation](references/testing-and-documentation.md).

The [application structure guide](../../../docs/development/application-structure.md#component-conventions) owns canonical conventions. [Application Contracts](../inframeld-application-contracts/SKILL.md) supplies service and transaction workflows when needed. Existing frontend guidance remains separate.
