# ADR-0079: Protect Deployment transitions with a focused aggregate

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Production has current A, previous Z and candidate B. Promotion, rollback and mode switches must preserve related serving/control state. The accepted rules define valid outcomes and publication guards, but had not selected where transition behavior belongs.

## Considered Options

- A focused Deployment aggregate owns related mode/serving state and protects valid transitions, while an application service supplies current authority/readiness facts. This groups cohesive state but requires a precise loading/save contract. This is selected.
- Pure transition policies consume immutable state and return changes, with application services coordinating persistence. This keeps coordination visible but requires preventing callers from bypassing the transition policies.

## Decision Outcome

Use a focused Deployment aggregate for related serving/mode/control state and its valid domain transitions. An aggregate is the domain object responsible for state and rules that must remain consistent. The application service obtains current authorization, readiness and dependency facts, loads the necessary Deployment state, invokes its business behavior and saves through a specific repository. The service owns the transaction. The repository persists without committing or retrying.

Pure policies remain appropriate for decisions using explicit external facts. Current authorization, dependency checks and job admission remain application responsibilities. Do not load every Pipeline, document or job into the aggregate. The current logical Deployment records own the state requirements. Creation constructs new state under the existing first-ready-version/default-binding rules rather than loading a nonexistent Deployment.

## Consequences

Specify the aggregate's exact state/loading/save contract and how concurrent publication, mode changes and operator commands share the control check. Preserve atomic pointer/history/completion changes, expected revisions, newest-request/attempt fences and current health/authority checks. This decision selects no table layout, locking algorithm or endpoint and changes no existing mode, canary or rollback behavior. Runtime implementation and concurrency qualification remain unfinished.

This records accepted target architecture. Implementation and qualification remain unfinished. Existing product decisions remain authoritative, and no earlier ADR is superseded.

## Links

- [Current owning guide and remaining design](../../.agents/skills/inframeld-releases/references/architecture.md#deployment-transition-boundary).
- [Logical records](../../.agents/skills/inframeld-releases/references/records-and-transitions.md#releases).
- [Module architecture](../../.agents/skills/inframeld-releases/references/architecture.md).
- [Application/component conventions](../../.agents/skills/inframeld-coding-standards/references/component-roles-and-imports.md#component-conventions) and [modular-backend decision](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
