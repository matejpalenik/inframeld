# ADR-0001: Strict DDD, Clean Architecture, and lightweight CQRS

**Status:** Accepted — modular structure, dependency rules, and feedback ownership.  
**Revised:** 19 September 2026.  
**Required approach:** Strict DDD, Clean Architecture, lightweight CQRS, and Docker Compose-only delivery.  
**Related:** [Architecture guide](../ARCHITECTURE.md), [durable jobs and recovery](ADR-0007-durable-jobs-idempotency-and-recovery.md), [deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md).

## Context

Inframeld processes documents into searchable knowledge, runs pipelines that retrieve information and generate answers, and supports evaluating and releasing pipeline versions.

The API, background worker, and user-facing interfaces all need to work with the same business rules. A release should follow the same rules regardless of which interface requests it. A screen that combines evaluation and release information should not become another owner of that information.

This architecture decision record (ADR) explains how we organize the code, where those rules belong, and how the backend's business areas work together. It refines the existing **modular monolith**: one backend codebase divided into modules with clear responsibilities.

Strict DDD, Clean Architecture, lightweight CQRS, and Docker Compose-only delivery are already approved requirements. This record explains how to apply them without adding unnecessary patterns or infrastructure. It does not select an identity provider or storage product; those choices belong to their respective ADRs.

## Decision

**One Python backend owns the product's business behavior.** Its modules have clear state ownership, its dependencies point toward business rules, and its read and write paths serve different purposes without requiring separate relational databases.

### 1. Runtime structure

The backend runs as two separate processes, built from the same backend image:

- **API:** Handles incoming application requests.
- **Worker:** Executes backend work outside the API request process, using the same application use cases and domain rules.

The small Next.js console, **Studio**, handles presentation and browser-session integration. It is not a second implementation of the backend's business logic.

A separately isolated parser performs untrusted document conversion under ADR-0010. It converts documents; it does not own business state.

**Docker Compose is the only supported deployment method.**

### 2. Architecture principles and dependency rules

**Domain-Driven Design (DDD)** organizes code around the product's concepts and rules: documents, indexes, pipelines, evaluations, releases, and access. Each business area has a clear owner.

**Clean Architecture** keeps those business rules independent of the technologies used to expose, store, or execute them. Changing a web framework or storage adapter should not require moving business rules into that technology.

**Lightweight CQRS**, short for _Command Query Responsibility Segregation_, separates operations that change state from operations that read it. It does not require separate databases or a messaging system.

**“Strict” means we enforce dependencies and ownership. It does not mean every concept needs every possible design pattern.**

#### Which code may depend on which

The dependency direction is:

```text
HTTP / browser-session adapters
    -> application commands and queries
        -> domain rules and values

PostgreSQL / Chroma / model / artifact adapters
    -> application-owned ports

Composition root
    -> concrete implementations and configuration
```

These arrows describe code dependencies, not the order of network calls.

The **domain** contains business rules and values. It must not import FastAPI, an object-relational mapper (ORM), Chroma, Docling, LiteLLM, or identity-provider libraries.

The **application layer** implements use cases: the steps needed to carry out a requested operation. Its contracts use application-owned values, not objects defined by external services or libraries.

A **port** is an application-owned interface describing a capability the application needs, such as storing an artifact or calling a model. An **adapter** implements that interface using a particular technology. Infrastructure adapters translate external types into application-owned values at the boundary.

The **composition root** is the startup code that creates the concrete implementations, supplies their configuration, and connects them. Dependency injection means explicitly passing those dependencies to the objects that need them. Domain code must not look up services through a service locator or framework container.

### 3. Business areas and state ownership

Each area owns a defined set of business facts and rules. These are bounded areas inside one codebase, not separate microservices.

| Area | What it owns |
| --- | --- |
| **Knowledge** | Source identity; document lifecycle and versions; collection revisions and their document memberships. |
| **Indexing** | The settings and state needed to prepare searchable indexes: processing and embedding profiles, processing generations, vectorizations, layouts, materializations, publication, and reconciliation. |
| **Pipelines** | Immutable pipeline configuration and its links to prepared indexes (materialization bindings); retrieval and generation orchestration. It also owns answer receipts and their current feedback records, as explained below. |
| **Evaluation** | Datasets, evaluation-run evidence, metric results, and comparisons. |
| **Releases** | Deployments, candidate cohorts (groups routed to a trial version), promotion, candidate abort, and rollback. |
| **Access** | Mapping callers to application principals; organization and project scope; permission decisions. |

A **principal** is the identity the application recognizes as the caller. An **index materialization** is a concrete searchable index prepared for particular knowledge and processing/embedding settings. **Reconciliation** checks and resolves inconsistencies between the recorded index state and the actual stored state.

Processing and indexes may be separate submodules inside Indexing. However, **only Indexing decides whether a materialization is ready**.

#### How modules work together

To request a change owned by another module, use that module's public application operations. Unrelated modules must not update each other's tables directly.

Shared identifiers and a small value carrying the current request's scope are acceptable. A shared package containing everyone's domain models is not: it would make ownership unclear and couple otherwise separate business areas.

Jobs and audit persistence are supporting application capabilities. They do not create additional owners of evaluations, deployments, or other business state.

The same rule applies to an evidence screen. It may read projections from several owning modules, but an `evidence` module must not become another writer of evaluation or deployment state. Combining information for display does not transfer ownership of that information.

### 4. Business rules, aggregates, and transactions

#### Use domain objects where they enforce real rules

An **invariant** is a business rule that must remain true when an operation completes. An **aggregate** is the boundary within which related state and behavior enforce those rules.

For example, a `Deployment` owns the rules for:

```text
attach_candidate
set_canary
abort_candidate
promote
rollback_promotion
```

Here, a Deployment controls which pipeline version serves requests; it is not a Docker deployment. Its transition rules belong in the domain object, not independently in an API handler and a worker.

A `PipelineVersion` validates its immutable configuration. By contrast, a source span—the location an excerpt came from—or a recorded metric can be a plain immutable value. Neither needs an elaborate object hierarchy merely to hold data.

#### An aggregate does not mean loading every related row

An aggregate boundary defines which rules must be protected. It does not require loading every related record into memory.

A collection containing one million documents should load a small aggregate root and a revision reference, not one million document objects. Membership creation, verification, and reads use streaming or set-based repository operations, keeping memory use bounded.

The aggregate root controls the rules; repository operations handle the volume of data.

#### Keep database transactions short

Application commands define short PostgreSQL transactions. A transaction groups database changes so they commit together or do not commit at all.

The domain explains and validates the business rules. Database adapters also enforce them through uniqueness constraints, foreign keys that preserve organization/project relationships, and conditional updates that only succeed against the expected revision.

Both layers matter. A domain check can reject an invalid action, but another request may change the database immediately afterwards. Database constraints and conditional updates protect the rules when requests run concurrently.

**Admission** means durably accepting an operation. Command admission, its job row, the recorded idempotency outcome, and any required audit event may commit in the same transaction. The idempotency outcome records what a retry of that same operation should receive.

There is no need to split these records into an eventually consistent workflow—where some records catch up later—when one application transaction already owns the changes.

#### Keep external calls outside long SQL transactions

Storage and model calls must not hold a long-running SQL transaction open. Recording that the work was accepted and recording its completion are separate durable steps, with the external work between them.

The worker invokes the same application commands as the API. This includes admitting new source identities discovered during synchronization. It must not create an alternative domain model or allocate a new identity every time an operation is retried.

### 5. Lightweight CQRS: different paths for changing and reading state

A **command** changes state through an application use case and the relevant domain behavior. Promoting a candidate is a command.

A **query** reads a useful view of state. Loading the deployment table in Studio is a query.

Queries return purpose-built **data transfer objects (DTOs)**: values shaped for the information the caller needs. These come from authorization-scoped read projections in the same PostgreSQL database. A read projection is a view of stored data arranged for a particular read operation.

A query does not need to rebuild a Deployment aggregate merely to display a row in a table. It can read the required fields directly, while enforcing the caller's permissions.

Queries may join records from different business areas. Those joins belong in explicitly owned read adapters. **Permission to read across modules does not grant permission to write across them.**

This approach does not require a message bus, mediator framework, event sourcing, a separate relational read database, or a generic saga engine for coordinating multi-step workflows.

Chroma is a necessary exception to keeping projections in PostgreSQL: it holds derived search data and has its own explicit consistency protocol. Having that search projection does not require every other query to become eventually consistent.

### 6. Other interfaces, evaluation adapters, and answer feedback

#### MCP and Studio use the existing application

First-party **MCP**, the Model Context Protocol, is another incoming adapter alongside HTTP. It invokes the same application use cases. Pipelines still owns retrieval and answer generation, and Access still owns permission decisions.

Studio calls the application HTTP API through the official generated TypeScript **SDK**, a client library for working with the backend.

SDK Kit is the external tooling for generating those client libraries. **It is a blocker for Studio implementation, not backend implementation.** Backend work can proceed while that dependency is resolved.

Repository skills and their drafts are accepted development context: guidance for working on the repository, not modules in the running product.

The MCP integration profile is accepted in [ADR-0018](ADR-0018-first-party-mcp-adapter.md).

#### Evaluation adapters

OpenEvals and configurable GPT-6 Luna are the selected evaluation adapters for qualification. Qualification means checking their behavior against the product's requirements; selection alone does not establish that behavior.

#### Answer feedback has a single owner

Answer feedback is part of v1. Its ownership follows the existing business boundaries:

| Area | Responsibility for answers and feedback |
| --- | --- |
| **Pipelines** | Owns the existing `AnswerReceipt`, the record associated with a served answer, and its current `Feedback` record. |
| **Releases** | Supplies the immutable routing selection that identifies which version served the answer, and owns subsequent release transitions. |
| **Evaluation** | Owns offline evaluation evidence, rather than production answer feedback. |
| **Studio** | Reads authorized projections across these records. It does not become another authority for the underlying evidence. |

The detailed feedback contract is accepted in [ADR-0017](ADR-0017-answer-feedback.md).

### 7. Default onboarding and publication modes use existing application behavior

The default first-use experience is:

```text
Configure models -> Upload documents -> Ask a question
```

This uses the ordinary resources owned by Access, Knowledge, Indexing, Pipelines, and Releases. It does not create a parallel, simplified implementation of the product.

[ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) accepts reversible **Automatic updates** and **Manual releases** for each Deployment. The default onboarding path starts automatic. An explicitly created Deployment starts manual unless its creator chooses automatic. The mode belongs to the Deployment, so two endpoints using the same Pipeline can have different release controls.

#### Automatic updates compose normal build and release operations

A completed, authorized upload batch or explicit **Save and apply** action freezes a complete corpus and the selected configuration. Application code records that update through the existing durable jobs, calls the ordinary build behavior, and then separately asks Releases to publish the ready result. The actor needs the relevant source/configuration permissions and build/deploy authority for the selected target; automatic mode grants no additional rights.

**A successful build establishes readiness, not permission to change traffic.** Releases checks that Automatic updates is still selected, along with current authorization, readiness, deletion state, job ownership, the captured control and serving revisions, the newest authorized update identity, and the absence of an attached candidate before committing publication and history together. A failed or superseded update leaves the healthy serving version unchanged. Failure of newer work cannot revive an older update's publication authority.

For example, replacing one document can prepare P13 while P12 continues serving. The automatic update can publish P13 only after its complete build succeeds and those release checks still pass. This same application composition supports first publication and later updates; there is no separate Prepare and ask command, first-use-only coordinator, or workflow engine.

#### Switching modes preserves the endpoint and its history

Switching to **Manual releases** leaves the current version serving and invalidates pending automatic publication. A build may still finish and produce reusable ready artifacts. The **Enable automatic updates and apply pending changes** action freezes the displayed inputs into a fresh authorized request; it never restores an old job's authority. The current version remains available while that request is prepared. These commands use idempotency and expected-revision checks, and each successful mode switch advances the publication control revision.

An attached candidate, even at 0% traffic, blocks enabling automation. Candidate attachment, canaries, promotion, rejection and rollback require manual mode. Rollback leaves the Deployment manual. Explicit comparisons remain available in either mode, but neither evaluation scores nor answer feedback authorize publication.

#### Defaults identify ordinary resources without inventing readiness

A **project-default binding** records stable resource IDs as small, project-scoped application configuration. Before a real Deployment exists, it also holds the selected publication mode and control revision, and the logical default route reports not ready. First successful publication creates a Deployment with one genuinely ready current version, no candidate and no previous target, transferring control state from the binding atomically. The binding and Deployment never become independent authorities for the same mode.

Knowledge still owns source membership, Indexing owns materialization readiness, Pipelines owns frozen builds and answer execution, and Releases owns traffic changes. HTTP, Studio and workers invoke these application operations rather than introducing a separate onboarding domain or retrieval path. ADR-0019 contains the detailed concurrency and transition rules.

#### Persistent outbound credentials

Outbound credentials are secrets Inframeld uses when calling another system, such as a model provider. Persisting them is a required supporting application capability.

The encrypted-store implementation using **PostgreSQL and PyNaCl is accepted** in [ADR-0020](ADR-0020-persistent-outbound-credentials.md).

Responsibilities remain separate: Access supplies permission decisions; connection commands own credential references; and the storage adapter owns the cryptographic representation.

Domain snapshots must not contain plaintext secrets or secret-management SDK objects. They use references rather than embedding credentials or external secret-storage types in the domain model.

### 8. Keeping the code understandable and verifying the boundaries

Use names from the domain, keep related behavior together, return explicit errors, and keep interfaces focused on a clear responsibility.

Small functions can help readability, but there is no numerical rule for an acceptable function size. Comments and ADRs should explain **why** a consistency or security rule exists. Avoid duplicate DTO layers when they provide no meaningful translation or separate responsibility.

Tests should demonstrate business behavior, not just that methods were called. Examples include:

| Scenario | Behavior to verify |
| --- | --- |
| A promotion uses an outdated deployment revision. | The stale promotion is rejected. |
| A materialization has not been published. | It is unavailable for serving. |
| An operation references a resource from another project. | The cross-project reference is denied. |
| A process restarts and retries publication. | Publication is not duplicated. |

Add automated dependency checks for forbidden imports and dependency cycles.

Boundary tests must use real PostgreSQL and the Chroma server shipped with the product. Mock-only tests cannot establish whether the actual database constraints, concurrency behavior, or Chroma operations satisfy the required semantics.

## Consequences

### Positive

- **Background work is separated from request handling.** Separate API and worker processes protect request responsiveness while using the same backend code and image.
- **Changes stay with their business owner.** Clear module ownership keeps business rules and state changes in the area responsible for them.
- **Read paths can fit the screen or caller without another relational database.** Lightweight CQRS allows purpose-built read shapes while avoiding the synchronization burden of a separate read database. Chroma remains a derived search projection with its own consistency protocol.

### Negative

- **Separate processes add packaging work.** The API and worker need distinct runtime entry points even though they share a backend image.
- **Module ownership requires discipline.** Developers must use the owning module's application operations rather than update its tables from elsewhere. Dependency checks and behavior tests are part of enforcing that boundary.
- **Read and write models are deliberately different.** Developers maintain query DTOs alongside command-side domain behavior. Additional DTO layers are still unnecessary when they add no translation or responsibility.
- **Future service extraction is not free.** Ports make dependencies explicit, but moving a module into a separate service later may still require refactoring.

## Alternatives considered

The approaches below are excluded or not required by this decision. No separate comparative evaluation is recorded.

### Separate microservices for each business area

**Not selected.** Knowledge, Indexing, Pipelines, Evaluation, Releases, and Access are modules in one Python backend, not six independently deployed services.

Running the API and worker as separate processes does not change that ownership model. Future service extraction remains possible, but the current boundaries do not guarantee that it would require no refactoring.

### Put business rules in frameworks or delivery interfaces

**Ruled out.** FastAPI handlers, worker entry points, Studio, and MCP must not maintain separate implementations of the same business rules. They use the existing application use cases.

Likewise, domain code must not depend on ORM, storage, model, parser, or identity-provider libraries. Application-owned contracts and infrastructure adapters keep those technologies at the boundary.

### Require a larger CQRS and messaging stack

**Not required.** Separating commands from queries does not require a message bus, mediator framework, event sourcing, a separate relational read database, or a generic saga engine.

The selected approach uses authorization-scoped PostgreSQL read projections. Chroma has its own search-consistency protocol, but its existence is not a reason to make every query eventually consistent or split related PostgreSQL changes into separate commits.

### Load complete aggregates for every operation

**Not required.** An aggregate defines the rules that must remain true; it does not require loading every related row. Loading a million document objects to work with one collection would conflict with the requirement to keep memory use bounded.

Collection membership operations use streaming or set-based repository operations. Queries can return authorized projections without rebuilding aggregates merely to display a table.

### Create additional evidence or onboarding domains

**Ruled out.** An evidence screen reads records owned by the existing modules; it must not become a second writer of evaluation or deployment state.

Similarly, default onboarding coordinates ordinary application operations. It is not another business domain, alternative retriever, or general workflow engine. These boundaries let the interfaces combine existing behavior without creating competing owners.

## References

[Martin Fowler's explanation of CQRS](https://martinfowler.com/bliki/CQRS.html) describes separate command and read models and why the pattern should be applied selectively. The specific module boundaries and ownership rules in this ADR are Inframeld design choices.
