# PD-INDEXING-01: Exchange complete prepared bindings between Indexing capabilities

**Status:** ACCEPTED

**Approval date:** 2026-10-29

**Owner:** `inframeld-indexing`

**Issue kind:** Implementation contract.

The developer explicitly approved this proposal and its detailed batch-3 contract on 2026-10-29, then requested repository and GitHub recording. [ADR-0107](../../../../docs/adr/ADR-0107-reference-exact-verified-index-materializations.md) records the decision. Acceptance selects logical behavior, not implemented code or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice prepares R2 with a selected processing and embedding profile. A query needs the exact verified generations, while cleanup needs to know which bindings are still retained. Passing just “collection Support is ready” would let later settings or a different revision change the meaning.

Preparation, retrieval and retirement are accepted separate capabilities. Their exact trusted inputs, complete results, unavailable outcomes and resource lifetime contracts are selected by the approved resolution below. A partial binding could accidentally substitute newer data, omit a required shard or confuse readiness with publication authority.

## Accepted context and evidence

PostgreSQL owns exact membership and state. Chroma holds immutable derived records. The singleton worker writer owns vector mutation. Profiles, numerical executions, layouts and materializations have different identities. Current access and health remain required even after readiness verification.

A typed binding is a named application-owned description of exact dependencies, not a permission certificate or new aggregate per field. Keep ORM/vendor types out of application contracts and all remote embeddings behind ModelGateway. ADR-0076 selects the capability split, not its signatures.

## Alternatives and trade-offs

1. **Pass one complete immutable prepared-binding result.** Return the verified identities and references required by callers as a coherent application value. This makes completeness visible, but must stay bounded rather than embedding an entire corpus.
2. **Pass a stable binding identity and resolve through a scoped reader.** Callers retain a small identity and load the exact verified projection when needed. This keeps messages compact, but adds a read and requires explicit unavailable/currentness behavior.

<a id="non-binding-recommendation"></a>

## Approved resolution

Use the existing IndexMaterialization identity as the small immutable prepared-binding reference, scoped to its organization and Project. Resolve it through an application-owned scoped reader. Do not introduce a second duplicate binding aggregate. A consumer's complete binding set identifies every required materialization for its captured corpus. Preparation returns ready references only when all required verification has completed, otherwise a typed pending or safe failure/unavailable result with the original operation identity where admitted.

The trusted projection identifies the exact CollectionRevision and membership manifest, processing-profile revision, embedding profile, VectorIndex and immutable VectorLayout. It references exact processing/vector generations, expected and verified manifest identities/hashes and counts, per-shard verification completion and observed dependency-health generation. Use the existing record vocabulary. Distinguish immutable verification evidence from current lifecycle/health observations. Every required shard and generation must be represented. A count alone is insufficient verification.

Keep large generation/record inventories in immutable manifests, accessed in bounded pages. Return compact references and the caller's necessary typed projection, without copying the full corpus or leaking vendor/ORM objects into application contracts. Public DTOs and concrete field names remain owned by normal interface delivery. A client-supplied binding ID is never trusted as authority.

Resolve the exact selected binding and acquire the operation's pin in one short SQL transaction through the same retention gate used by ordinary cleanup. Admit a pin only while its selected dependencies remain usable. The operation owns the pin and its attempt/deadline/fence. Active operation pins and retained Deployment/build/rollback references protect against ordinary retirement. Release active pins when use finishes. A retained snapshot's metadata alone does not preserve numerical data forever.

Do not expire an abandoned pin solely because its database lease elapsed. Expiry requires an enforced stop of further reads/outbound content and rejection of late results. If that cannot be established, retain the pin or stop and drain the old runtime. Explicit erasure/revocation retains its overriding protection rules.

Retrieval derives permitted generation filters from current server-owned authorization and the exact saved binding. It must not follow a newer collection pointer, silently substitute another physical generation or return a partial index because a required shard is unavailable. Missing, incompatible, retired or unconfirmed required dependencies produce a safe unavailable/failure result. New preparation is an explicit ordinary admitted operation, not hidden work performed while resolving an old binding.

Readiness is neither permission nor a promise of continuing health. Recheck authority and the accepted dependency-health generation at the existing boundaries, including after retrieval, before provider disclosure and before returning an answer. Changed invalidating health discards affected results. Keep network waits outside SQL transactions. PD-INDEXING-02 still owns what observation can detect in the supported backend. This decision does not invent continuous full-vector validation or claim that unknown corruption is detectable.

## Alice and Bob example

Alice starts a query using M1 for R1. Bob prepares R2 as M2. Alice keeps M1, even if the collection's current selection moves to R2. Cleanup cannot ordinarily remove M1 while her valid pin is active. If one of M1's required shards becomes unavailable, her query fails safely instead of quietly answering from half the corpus or switching to M2.

## Decision trigger and stopping boundary

Apply this accepted contract when the original trigger matches. Concrete method names and physical schemas remain ordinary implementation choices under the repository conventions. Do not reopen the approved policy. Separately pending neighboring choices retain their own triggers. Qualification gaps limit release claims, not authorized evidence gathering.

## Architectural impact and dependencies

Indexing application ports/readers, Pipeline captured inputs, build completion, Evaluation preparation and cleanup. Update component and preparation/query sequences without inventing a process per capability.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-02 (accepted): Define what current index health can actually detect](decision-health-observation.md). For current-health meaning.
- [PD-PIPELINES-01 (accepted): Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For the consuming execution/build input contract.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

These are required cases and evidence, not passing tests.

Complete versus partial shard verification, wrong-Project references, million-member paged inventories, preparation failure, query-versus-retirement races, deadline expiry while a call is active, source erasure, lost dependencies and unchanged query meaning after another revision becomes current.

## Sources and finalization

- [Accepted capability boundary](architecture.md#indexing-capability-boundaries).
- [Indexing records](records.md#indexing).
- [Capability decision](../../../../docs/adr/ADR-0076-separate-index-preparation-retrieval-and-retirement.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application edits, a paid qualification call or claims of successful runtime qualification.
