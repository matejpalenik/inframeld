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
- Separate distinct logical steps in backend Python functions with [one empty line](references/testing-and-documentation.md#group-logical-steps-within-python-functions). Keep closely related statements together.
- Keep [observations, workflow decisions and persistence](references/protocols-and-persistence.md#separate-observations-decisions-and-persistence) distinct. Readers report facts, application/domain components decide, and adapters retain persistence safeguards.
- Use dedicated value types when identity, invariants, secrecy or accidental mixing matter. Preserve enums/literals for closed vocabularies and documented primitive/serialization exceptions. Do not wrap every primitive for symmetry.
- Use standard frozen, slotted dataclasses for immutable records. Preserve runtime ID distinctions, secret-safe representations and the narrow accepted record-interface exceptions.
- Protocol implementations explicitly inherit their contract, implement required abstract members and mark overrides. Preserve strict Pyright. Use typed SQLAlchemy mappings/expressions under the exact persistence exception rules.
- Verify behavior through the repository's scaffold-first TDD sequence. Review organization manually rather than adding structural enforcement tests.

These conventions apply to backend Python suggestions and reviews as well as authorized implementation. They do not grant permission to write files. Existing code is not automatically migrated by a documentation change.

## Explain, suggest or review

1. Select the language and applicable directory guidance. For domain-specific backend component design, code generation or structural review, read the owning domain skill's architecture reference and relevant workflow. Shared components use [Application Contracts’ shared component view](../inframeld-application-contracts/references/components-and-services.md), with its transaction/job or gateway reference when applicable. Read domain context when product behaviour matters. Use accepted architecture and inspected implementation as their status permits. A proposal awaits a decision before code depends on it.
2. Before code depends on an unresolved domain/shared contract, load the matching pending decision from its owning skill and follow [the approval and consistency workflow](../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Raise only decisions relevant to this component. Qualification gaps do not prohibit tests of accepted requirements.
3. Select the component's role, destination, declaration and behavioral contract. For backend Python, read component roles. Load only the references needed for that choice. Their worked examples explain the situation, decision, code, flow and failures. Do not copy every grant collaborator into a workflow that does not need it.
4. Follow values from the external boundary through typed application contracts and back. Check current authority and resource ownership separately from type correctness.
5. Show complete contextual examples with exact paths, imports and placement. Distinguish inspected code from illustrative suggestions and future design.
6. Check failure behavior, typing and meaningful tests. Report the convention, its reason and its effect when reviewing a violation. Do not turn legitimate exceptions into blanket bans.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Aggregates and repositories | [Change an aggregate through its specific repository](references/aggregates-and-repositories.md) |
| Component roles and imports | [Choose a component and import its type](references/component-roles-and-imports.md) |
| Protocols and persistence | [Implement capabilities and typed persistence](references/protocols-and-persistence.md) |
| Services and use cases | [Write a service around a complete use case](references/services-and-use-cases.md) |
| Static utilities and mappers | [Static utilities, policies and mappers](references/static-utilities-and-mappers.md) |
| Testing and documentation | [Test behavior and explain the contract](references/testing-and-documentation.md) |
| Choosing test layers, dependency isolation or interpreting verification evidence | [Testing skill](../inframeld-testing/SKILL.md), only when that strategy question arises |
| Values and records | [Give values their domain meaning](references/values-and-records.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
