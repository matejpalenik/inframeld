# ADR-0075: Separate document lifecycle from collection selection

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Alice replaces handbook B1 with B2 while an earlier query retains R1={A1,B1}. Admitting source bytes and selecting exact collection membership are different state changes. A complete authorized batch may need both. The accepted lifecycle fixes their behavior, but the internal operation boundary was open.

## Considered Options

- One collection-oriented operation coordinates source/version and membership changes. This reduces initial wiring but couples document lifecycle to collection management.
- Focused document/version operations and collection-selection operations cooperate through an application workflow. This keeps each responsibility focused, at the cost of an explicit consistency and handoff contract. This is selected.

## Decision Outcome

Knowledge exposes focused application operations for document/version lifecycle and for exact collection selection. A coordinating application workflow handles accepted complete batches involving both. The operations preserve current audiences, atomic admission and immutable source/version identities. Replacing content does not silently retarget every collection or execution. CollectionRevision continues freezing exact DocumentVersions.

Choose aggregates around real consistency rules and bounded state, rather than making every DocumentVersion or manifest an aggregate. This decision does not select aggregate/repository signatures, create a table per concept or require loading an entire version history.

## Later contract resolution

Accepted [PD-KNOWLEDGE-01](../../.agents/skills/inframeld-knowledge/references/decision-complete-batch-handoff.md#approved-resolution) on 2026-10-29 fills the corresponding consistency/binding contract below. Earlier design-work statements retain their historical context. Implementation and qualification remain unfinished.

## Consequences

Specify the transaction/consistency boundaries, durable artifact handoff, committed batch-membership outcome and retry/recovery behavior before implementing the corresponding ports. Separate operations do not imply separate commits or permission to expose a partial batch as complete. Indexing preparation and Releases publication keep their own authority and lifetimes.

This records accepted target architecture. Implementation and qualification remain unfinished. Existing product decisions remain authoritative, and no earlier ADR is superseded.

## Links

- [Current owning guide and remaining design](../../.agents/skills/inframeld-knowledge/references/architecture.md#knowledge-operation-boundaries).
- [Logical records](../../.agents/skills/inframeld-knowledge/references/records.md#knowledge).
- [Module architecture](../../.agents/skills/inframeld-knowledge/references/architecture.md).
- [Application/component conventions](../../.agents/skills/inframeld-python-standards/references/component-roles-and-imports.md#component-conventions) and [modular-backend decision](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
