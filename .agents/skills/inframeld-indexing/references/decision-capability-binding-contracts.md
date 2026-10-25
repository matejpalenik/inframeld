# PD-INDEXING-01: Exchange complete prepared bindings between Indexing capabilities

**Status:** PENDING

**Owner:** `inframeld-indexing`

**Issue kind:** Implementation contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice prepares R2 with a selected processing and embedding profile. A query needs the exact verified generations, while cleanup needs to know which bindings are still retained. Passing just “collection Support is ready” would let later settings or a different revision change the meaning.

Preparation, retrieval and retirement are accepted separate capabilities. Their exact trusted inputs, complete results, unavailable outcomes and resource lifetime contracts remain to specify. A partial binding could accidentally substitute newer data, omit a required shard or confuse readiness with publication authority.

## Accepted context and evidence

PostgreSQL owns exact membership and state. Chroma holds immutable derived records. The singleton worker writer owns vector mutation. Profiles, numerical executions, layouts and materializations have different identities. Current access and health remain required even after readiness verification.

A typed binding is a named application-owned description of exact dependencies, not a permission certificate or new aggregate per field. Keep ORM/vendor types out of application contracts and all remote embeddings behind ModelGateway. ADR-0076 selects the capability split, not its signatures.

## Alternatives and trade-offs

1. **Pass one complete immutable prepared-binding result.** Return the verified identities and references required by callers as a coherent application value. This makes completeness visible, but must stay bounded rather than embedding an entire corpus.
2. **Pass a stable binding identity and resolve through a scoped reader.** Callers retain a small identity and load the exact verified projection when needed. This keeps messages compact, but adds a read and requires explicit unavailable/currentness behavior.

## Non-binding recommendation

**Proposal only.** Prefer a bounded stable identity plus the explicit verified projection each caller actually needs. Select fields and lifecycle through one preparation-to-query example and one retirement race. Neither option may follow mutable pointers or treat the binding as access authority.

## Decision trigger and stopping boundary

Before defining preparation, retrieval or retirement application ports and their complete input/result records.

Pause incomplete binding/result interface design. Existing profile and immutable-generation requirements stay accepted.

## Architectural impact and dependencies

Indexing application ports/readers, Pipeline captured inputs, build completion, Evaluation preparation and cleanup. Update component and preparation/query sequences without inventing a process per capability.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-02: Define what current index health can actually detect](decision-health-observation.md). For current-health meaning.
- [PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For the consuming execution/build input contract.

## Open questions and required evidence

- Which identities and verification facts must every caller receive?
- Which data is referenced versus copied, and how are sizes bounded?
- What happens when a selected dependency is unavailable or retired?
- Who holds/releases the pin and owns external-call boundaries?

## Sources and finalization

- [Accepted capability boundary](architecture.md#indexing-capability-boundaries).
- [Indexing records](records.md#indexing).
- [Capability decision](../../../../docs/adr/ADR-0076-separate-index-preparation-retrieval-and-retirement.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
