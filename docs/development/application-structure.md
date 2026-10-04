# How the application is organized

Use this guide to find the code that should own a change. Start with [the product overview](../ARCHITECTURE.md), then follow Alice's upload below. The [data model](data-model.md) defines records, and [API contracts](api-contracts.md) defines how clients call the backend.

Alice updates a handbook in Support. Knowledge records the document, Indexing prepares it for search, and a later release may make the new version live. Keeping these responsibilities separate lets us change one part without giving it control over the others.

Sections 1–2 explain the owners and follow a request. Sections 3–5 explain how to save changes safely and review an implementation.

> **Design status:** These are accepted v1 design rules. The component map and human-session flow describe the implemented backend foundation. The upload, worker, and later domain journeys describe accepted behavior that still needs implementation and verification where noted.

## Contents

| Reader’s question | Start here |
| --- | --- |
| Where does my change belong? | [1. One backend, several owners](#model) |
| Which component should I open? | [Component map and conventions](#component-conventions) |
| How does a human-session request work? | [Implemented authentication flow](#authentication-flow) |
| How does work reach its owner? | [2. Follow a command and a query](#operation) |
| Where do transactions start and end? | [3. Keep changes consistent](#coordination) |
| What belongs in HTTP, Studio, or MCP? | [4. Share behavior across entry points](#entry-points) |
| How do I review a change? | [5. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [6. Decision and reference map](#decision-map) |

<a id="model"></a>

## 1. One backend, several owners

The backend runs as two separate processes, built from the same backend image:

- **API:** receives application requests.
- **Worker:** carries out background work using the same application operations and business rules.

The Next.js console, **Studio**, handles presentation and browser-session integration - it is not a second implementation of the backend's business logic.

A separate, restricted parser converts uploaded files. Because documents can be malicious, it runs within the [document-processing restrictions](ingestion-security.md) and cannot change application business records.

**Docker Compose is the only supported deployment method.**

### Architecture principles and dependency rules

**Domain-Driven Design (DDD)** organizes code around the product's concepts and rules: documents, indexes, pipelines, evaluations, releases, and access. Each business area has a clear owner.

**Clean Architecture** keeps those business rules independent of the technologies used to expose, store, or execute them. Changing a web framework or storage adapter should not require moving business rules into that technology.

**Lightweight CQRS**, short for _Command Query Responsibility Segregation_, separates operations that change state from operations that read it. It does not require separate databases or a messaging system.

These rules make ownership and dependencies strict. They do not require extra design patterns for their own sake.

### Which code may depend on which

The dependency direction is:

```text
HTTP / browser-session adapters
    -> application commands and queries
        -> domain rules and values

PostgreSQL / Chroma / model / artifact adapters
    -> application-owned ports

Bootstrap composition root
    -> concrete implementations and configuration
```

These arrows describe code dependencies, not the order of network calls.

The **domain** contains business rules and values. It must not import FastAPI, an object-relational mapper (ORM), Chroma, Docling, LiteLLM, or identity-provider libraries.

The **application layer** carries out requests through **use cases**, the steps for an operation such as accepting an upload. Its inputs and results use values defined by Inframeld, rather than objects from a web framework or vendor library.

A **port** describes a capability the application needs, such as saving a file or calling a model. An **adapter** provides it using a particular technology. For example, an adapter translates a provider's response into the result type the application expects.

Startup code creates and connects these implementations. This is the **composition root**. Passing the required objects into a use case is called **dependency injection**. Domain code receives its dependencies directly rather than looking them up in a service locator or framework container.

<a id="component-conventions"></a>

### Finding a component in the implemented backend

Follow **domain → layer → component role**. First choose the owner, then the layer, then the job the component performs. To follow a business workflow, open its application service; to inspect a collaborator's contract, open its protocol. Authentication and authorization share these role folders inside Access.

The layout below shows the main components under `apps/backend/src/inframeld_backend/`. Individual row mappings and some shared adapters are abbreviated. Create a role folder only when implemented code needs it.

```text
inframeld_backend/
├── main.py
├── migrate.py
├── bootstrap/                         # construction, assembly, settings, lifecycle
│   ├── application_factory.py
│   ├── application_settings.py
│   ├── access_composition.py
│   ├── access_components.py
│   ├── application_resources.py
│   └── application_lifespan.py
├── access/
│   ├── domain/
│   │   ├── entities/principal.py
│   │   ├── value_objects/             # PrincipalId, ProjectId, ActionId, identity values
│   │   ├── enums/                     # PrincipalKind, PrincipalStatus, ProjectStatus
│   │   ├── policy_inputs/action_authorization_policy_input.py
│   │   └── policies/                  # named classes with pure static methods
│   │       ├── action_authorization_policy.py
│   │       ├── human_authentication_policy.py
│   │       └── project_visibility_policy.py
│   ├── application/
│   │   ├── services/
│   │   │   ├── human_session_authentication_service.py
│   │   │   ├── unavailable_human_session_authentication_service.py
│   │   │   └── action_authorization_service.py
│   │   ├── protocols/
│   │   │   ├── human_session_authenticator.py
│   │   │   ├── action_authorizer.py
│   │   │   ├── browser_session_verifier.py
│   │   │   ├── human_identity_link_reader.py
│   │   │   └── project_action_facts_reader.py
│   │   ├── dtos/
│   │   │   ├── access_context_dto.py
│   │   │   ├── verified_human_identity_dto.py
│   │   │   ├── project_action_target_dto.py
│   │   │   └── project_action_facts_dto.py
│   │   └── value_objects/browser_session_credential.py
│   ├── http/
│   │   ├── routes/current_session_routes.py
│   │   ├── dependencies/human_session_dependency.py
│   │   └── responses/current_session_response.py
│   └── infrastructure/
│       ├── readers/                   # PostgresHumanIdentityLinkReader, project facts reader
│       ├── verifiers/kratos_browser_session_verifier.py
│       ├── settings/kratos_settings.py
│       ├── rows/                      # one ORM row or mapping base per module
│       └── types/enum_types.py
└── shared/
    ├── domain/
    │   ├── errors/domain_errors.py
    │   └── validation/value_validation.py
    ├── application/
    │   ├── errors/
    │   ├── enums/application_error_code.py
    │   ├── dtos/command_context_dto.py
    │   └── value_objects/             # RequestId and OperationId
    ├── http/
    │   ├── routes/health_routes.py
    │   ├── dependencies/request_identity.py
    │   ├── middleware/request_context_middleware.py
    │   ├── requests/pagination_query.py
    │   ├── responses/                 # PageResponse, ProblemDetails, ValidationIssue
    │   ├── handlers/
    │   ├── mappers/
    │   ├── builders/
    │   ├── openapi/
    │   ├── definitions/               # problem definition and reviewed catalogue
    │   ├── types/                     # problem codes and bounded field aliases
    │   └── validation/
    └── infrastructure/
        ├── resources/database.py
        ├── settings/database_settings.py
        ├── migrations/migration_runner.py
        ├── rows/                      # Alembic's version row and mapping base
        ├── errors/
        ├── logging/
        ├── diagnostics/
        ├── timing/
        └── types/logging_types.py
```

### Component roles and naming

Use one primary public type per production module, with a matching snake-case filename. Entities, IDs, enums, and policy inputs have separate defining modules. Cohesive exception families, private helpers, constants, and framework type aliases may remain grouped. Import from the defining module; do not retain compatibility aliases after an internal move.

| Role | Naming and example | Responsibility |
| --- | --- | --- |
| Application operation | Capability-named protocol: `HumanSessionAuthenticator`, `ActionAuthorizer` | Specify public inputs, results, failures, and ownership independently of HTTP and vendors. |
| Application service | `*Service`: `HumanSessionAuthenticationService` | Coordinate the complete workflow through injected protocols. |
| I/O capability | Specific protocol: `BrowserSessionVerifier`, `ProjectActionFactsReader` | State the external capability the application requires. |
| Entity | `Principal` in `entities/principal.py` | Hold account state with stable identity; equality follows its ID. |
| Value object | `PrincipalId`, `IdentitySubject`, `BrowserSessionCredential` in `value_objects` | Give a value its meaning and enforce its invariants. |
| Enum | `PrincipalStatus` in `enums/principal_status.py` | Define a closed vocabulary. |
| Application DTO | `*DTO` in `dtos/*_dto.py` | Carry named operation inputs, results, or caller/command context. |
| Dedicated policy input | `*PolicyInput` in `policy_inputs/*_policy_input.py` | Supply the values a domain policy needs for its decision. |
| Policy | `*Policy` in `policies/*_policy.py` | Make a pure decision through static methods with explicit inputs. |
| Adapter | Technology-prefixed `PostgresHumanIdentityLinkReader`, `KratosBrowserSessionVerifier` | Perform I/O and convert external values at the boundary. |
| HTTP dependency | `*Dependency` | Extract request inputs and invoke an application operation. |
| Routes | `*_routes.py` | Register endpoints and translate their inputs and outputs. |
| HTTP model | `*Request` / `*Response` | Validate or serialize the wire contract using Pydantic. |
| Middleware | `*Middleware` in `*_middleware.py` | Wrap the ASGI request lifecycle. |
| ORM mapping | `*Row` in `infrastructure/rows` | Map persisted fields using typed constructors and expressions. |
| Settings | `*Settings` in `infrastructure/settings` | Validate resource configuration; bootstrap aggregates it. |
| Bootstrap assembly | `AccessComponents`, `ApplicationResources` | Group constructed collaborators and owned resources. These are not application DTOs. |

Existing published HTTP names such as `ProblemDetails` and `ValidationIssue` are preserved, including their OpenAPI descriptions. They do not acquire a DTO suffix. New HTTP models use Request/Response naming; application transfer records always use the uppercase `DTO` suffix.

A FastAPI dependency and ASGI middleware have different lifetimes. FastAPI invokes `HumanSessionDependency` for the route that declares it. `RequestContextMiddleware` wraps requests at the ASGI boundary. The authentication workflow belongs to `HumanSessionAuthenticationService`.

### Record roles: DTO, policy input, entity, and value object

A dataclass is an implementation mechanism, not a record's architectural role. Use standard `@dataclass(frozen=True, slots=True)` for application DTOs, policy inputs, and immutable value objects. Do not add custom decorators, marker bases, empty protocols, or generic record frameworks. Dataclass annotations do not perform runtime validation; value objects retain their explicit checks.

| Implemented record | What it means |
| --- | --- |
| `VerifiedHumanIdentityDTO` | The provider verified this authority/subject pair. Local account admission remains to be checked. |
| `AccessContextDTO` | The authenticated caller's principal ID, without cached status or permissions. |
| `ProjectActionTargetDTO` | The exact project selected for authorization; no proof of existence or visibility. |
| `ProjectActionFactsDTO` | Stored project/account status, membership, and exact-grant existence returned by a reader. |
| `ActionAuthorizationPolicyInput` | The eligibility and grant values the action policy consumes. |
| `CommandContextDTO` | Trusted request and operation identities used in command diagnostics. |
| `Principal` | A local account snapshot whose entity identity remains its `PrincipalId`. |
| `PrincipalId` | A UUID belonging to the principal identifier type, without proof that an account exists. |

Only `PolicyInput` identifies a dedicated policy input record. The word "Facts" in `ProjectActionFactsDTO` describes the reader's data; its DTO suffix makes its application boundary explicit. The service converts it into the policy input. Policies may also accept an existing entity or typed parameters directly: human admission accepts `Principal`, and project visibility accepts status and membership parameters.

[`Principal`](../../apps/backend/src/inframeld_backend/access/domain/entities/principal.py) contains its ID, organization, kind, and status. Equality and hashing use only its ID. The identifiers and enums live in separate files without weakening that cohesive entity. Pass the entity when a rule needs its state together; pass its ID when only identity is needed.

UUID IDs are frozen, slotted dataclasses wrapping a parsed UUID. Constructors reject raw strings, and equal UUIDs in different ID classes remain distinct. Preserve existing UUID versions and zero values. Parse and validate at external boundaries, then explicitly wrap/unwrap IDs at persistence and transport boundaries. Existence and authorization require their normal checks.

Identity authorities and subjects are separate value objects, grouped by `VerifiedHumanIdentityDTO` after provider verification. `BrowserSessionCredential` remains application-owned and hides its contents in representations and validation messages. Never log its explicit `.value`. `RequestId` and `OperationId` represent correlation, not authority.

### Qualified policy calls

Call pure business decisions through their policy class:

| Call | Decision |
| --- | --- |
| `HumanAuthenticationPolicy.may_authenticate(principal)` | Is the linked principal an active human? |
| `ProjectVisibilityPolicy.may_view_project(...)` | May this caller learn that the organization-scoped project exists? |
| `ActionAuthorizationPolicy.may_perform_action(policy_input)` | Does current eligibility include the exact requested grant? |

Policy methods use `@staticmethod`, explicit inputs, and no I/O or mutable class state. Services own orchestration and their injected collaborators. Ordinary conversion and validation helpers remain functions; adding a static policy convention does not turn all helpers into classes.

The following are the complete implemented declarations in `apps/backend/src/inframeld_backend/access/domain/policy_inputs/action_authorization_policy_input.py` and `apps/backend/src/inframeld_backend/access/domain/policies/action_authorization_policy.py`; they illustrate the convention and require no separate example files.

**`access/domain/policy_inputs/action_authorization_policy_input.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionAuthorizationPolicyInput:
    """Supply the current eligibility and exact grant needed to decide action admission."""

    principal_is_active: bool
    is_project_member: bool
    has_exact_action_grant: bool
```

**`access/domain/policies/action_authorization_policy.py`**

```python
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)


class ActionAuthorizationPolicy:
    """Require an active project member with the exact action grant."""

    @staticmethod
    def may_perform_action(policy_input: ActionAuthorizationPolicyInput) -> bool:
        return (
            policy_input.principal_is_active
            and policy_input.is_project_member
            and policy_input.has_exact_action_grant
        )
```

### Contracts and useful documentation

Operation and I/O contracts are explicit protocols. Required methods use `@abstractmethod`; implementations and test doubles explicitly inherit their protocol and mark overrides with `@override`. Strict Pyright checks those contracts. Protocols describe behavior; records do not acquire protocols just to label their role.

Document information a maintainer would otherwise have to infer: purpose, trusted inputs, what a result establishes, failure meaning, side effects, resource ownership, or a non-obvious invariant. Use direct human language, such as “Loads the current account status and project grants using the caller’s transaction.” Put the shared contract on the protocol and extra implementation details on the adapter.

Remove comments and docstrings that only repeat a name, signature, decorator, or obvious statement. A straightforward error subclass does not need its own docstring. Explain exceptions when the distinction affects handling, such as a dependency failure that does not establish whether retrying is safe. Keep useful test/fixture explanations, especially for unusual setup; there is no blanket requirement to document every declaration.

Before generating code, choose its owner, layer, role, destination, name, declaration style, and behavioral contract. Check its dependency direction and whether any documentation actually adds information. [AGENTS.md](../../AGENTS.md) makes these conventions mandatory for generated and suggested backend code.

### Typed persistence and boundary conversions

ORM rows stay inside PostgreSQL adapters and test support. Use `MappedAsDataclass` with keyword-only construction, typed `Mapped` fields, and database-generated fields excluded from initialization. Keep UUID columns as UUIDs; unwrap `.value` when constructing predicates/rows and wrap returned UUIDs when creating domain results. Enum mappings convert real stored values to enum instances and preserve existing database strings.

Use scalars, ORM records, or typed tuples and immediately construct named results. `PostgresProjectActionFactsReader` turns typed status and relationship expressions into `ProjectActionFactsDTO`; it never indexes a SQL result by arbitrary string keys. SQLAlchemy describes this type propagation in its [typed result documentation](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html#sql-expression-statement-result-set-typing).

Use SQLAlchemy inspection and typed expressions for connectivity, revision checks, and advisory locks. Alembic owns schema creation, including test-only constraints. Partial ORM read mappings are not a replacement schema or an autogeneration source for the authoritative initial migration.

The sole raw-statement exception is [`tests/support/postgres.py`](../../apps/backend/tests/support/postgres.py): PostgreSQL requires top-level database administration outside a transaction, so the isolated fixture composes `CREATE DATABASE` and `DROP DATABASE` with `psycopg.sql.Identifier`. Never interpolate identifiers or extend this exception to record queries or application code.

Dictionaries are appropriate at ASGI, JSON/OpenAPI, environment-framework, and logging serialization boundaries. Narrow dynamic values there. Any unavoidable framework `Any` or cast stays documented in that adapter. Application records and database results use named types.

<a id="authentication-flow"></a>

### Follow the implemented human-session request

```mermaid
flowchart TD
    Route["Current session route"] --> Dependency["HumanSessionDependency<br/>Extract browser credential"]
    Dependency --> Service["HumanSessionAuthenticationService<br/>HumanSessionAuthenticator protocol"]
    Service --> Verifier["BrowserSessionVerifier"]
    Verifier --> Kratos["KratosBrowserSessionVerifier<br/>Kratos SDK"]
    Service --> Reader["HumanIdentityLinkReader"]
    Reader --> Postgres["PostgresHumanIdentityLinkReader<br/>Independent read session"]
    Reader --> Principal["Principal<br/>ID, organization, kind, status"]
    Service --> Policy["HumanAuthenticationPolicy.may_authenticate"]
    Service --> Context["AccessContextDTO<br/>PrincipalId"]
```

Arrows represent calls or returned data inside one backend. Kratos and PostgreSQL are external services; the protocol and implementation boxes describe the same capability at two code boundaries.

1. Alice calls `GET /v1/session`. The FastAPI dependency reads the session cookie and creates an optional `BrowserSessionCredential`.
2. `HumanSessionAuthenticationService.authenticate` rejects an absent credential, then calls the injected verifier. The Kratos adapter runs the synchronous SDK call in a worker thread, checks expiry and provider identity state, and returns the verified authority/subject.
3. After verification completes, the reader opens a short independent database session. It finds the exact identity pair, constructs a `Principal`, and closes the session. No SQL session is held while waiting for Kratos, and concurrent requests never share an `AsyncSession`.
4. The service applies `HumanAuthenticationPolicy.may_authenticate`. A verified upstream identity needs an existing active local human account. The service returns `AccessContextDTO` containing that account's ID.
5. The route unwraps the ID into `CurrentSessionResponse`. The existing wire result remains `{"principalId": "<uuid>"}`.

Missing/rejected/expired credentials produce generic 401; absent links or ineligible local principals produce 403; unavailable/malformed provider responses produce 503. An explicit unavailable authentication implementation preserves 503 when Kratos configuration is absent. These outcomes use the shared [HTTP problem boundary](error-handling.md).

Authentication establishes the caller. A later `ActionAuthorizationService.require_action` reads current visibility, membership, account, and exact-grant facts. The service checks `ProjectVisibilityPolicy`, converts the reader DTO into `ActionAuthorizationPolicyInput`, then checks `ActionAuthorizationPolicy`. Hidden targets stay 404; visible targets without authority stay 403. Its PostgreSQL reader is bound to the caller's transaction session, unlike the independently scoped authentication reader.

### Resource ownership and test organization

Bootstrap creates stateless authentication services and adapters once per application. `Database` owns the pool and produces operation-local sessions. The lifespan starts the database compatibility check and always disposes the database and clears the actual Kratos SDK pool, including failed startup. The installed SDK context-manager exit does not release that pool. Construction and OpenAPI export perform no network calls; schema tools import `create_app` directly.

Unit tests mirror production layers and component roles. Integration tests are grouped under `access`, `postgres`, `kratos`, and `observability`, with distinct scenario filenames. Shared typed seed builders, isolated database provisioning, and validated browser-flow DTOs live under `tests/support`. Tests assert public JSON explicitly when the wire representation is the behavior under test.

`pnpm check:backend` runs formatting, lint, strict Pyright, fast behavioral/contract tests, and OpenAPI comparison. `pnpm test:integration` starts the isolated application PostgreSQL and Kratos stack, runs the complete suite, and cleans up services. CI invokes that same command. Review architecture and documentation manually; automated tests cover behavior, API contracts, resource cleanup, and actual integrations.

### Business areas and state ownership

The six areas below own different records and rules inside one codebase. These are not six separate microservices.

| Area | What it owns |
| --- | --- |
| **Knowledge** | Source identity, document lifecycle and versions, collection revisions and their document memberships. |
| **Indexing** | The settings and state needed to prepare searchable indexes: processing and embedding profiles, processing generations, vectorizations, layouts, materializations, publication, and reconciliation. |
| **Pipelines** | Immutable pipeline configuration and its links to prepared indexes (materialization bindings). Retrieval and generation orchestration. It also owns answer receipts and their current feedback records, as explained below. |
| **Evaluation** | Datasets, evaluation-run evidence, metric results, and comparisons. |
| **Releases** | Deployments, candidate cohorts (groups routed to a trial version), promotion, candidate abort, and rollback. |
| **Access** | Mapping callers to application principals, organization and project scope, permission decisions. |

A **principal** identifies the human or application making a request. An **index materialization** identifies search data prepared for particular documents and processing settings. **Reconciliation** means checking that recorded index state agrees with what is actually stored, then resolving any difference.

Processing and indexes may be separate submodules inside Indexing. However, **only Indexing decides whether a materialization is ready**.

### How modules work together

To request a change owned by another module, use that module's public application operations. Unrelated modules must not update each other's tables directly.

Modules may share IDs and a small value identifying the caller and relevant project. Putting every domain model into a shared package would make the modules depend on one another's internals and obscure who may change them.

Jobs and audit records support the application. They do not become another owner of evaluations, Deployments, or documents.

An evidence screen may combine information from several modules. Its read code can join their records, but it must not become another writer of evaluation or Deployment state. Showing information together does not change who owns it.

<a id="operation"></a>

## 2. Follow a command and a query

A **command** changes state. Alice's upload command checks her current permissions, saves source information, and records the background work to perform. A **query** reads state. Studio's progress request reads the upload's status without starting it again.

```mermaid
flowchart LR
    Entry[HTTP, MCP, worker] --> UseCase[Owning application use case]
    UseCase --> Domain[Domain rules]
    UseCase --> Port[Application-owned port]
    Adapter[PostgreSQL or vendor adapter] -. implements .-> Port
```

Solid arrows show calls. The dashed arrow means the adapter implements the port. These are parts of the code, not separately deployed services. Startup code supplies the adapters to the use cases.

### Lightweight CQRS: different paths for changing and reading state

Promoting a candidate version is a command. It runs through the owning use case and the domain rules for promotion.

Displaying Studio's Deployment table is a query. It needs a useful view of the current records, limited to what the caller may see.

A query returns a **data transfer object (DTO)**, a value containing the fields that screen or client needs. Its database reader selects permitted records from the same PostgreSQL database. Such a purpose-built view is called a **read projection**.

To display one Deployment row, the reader can select the required fields directly. It need not rebuild the full domain object, but it must still check permissions.

Read adapters may join records from different business areas. Each adapter still has an explicit owner, and being able to read across modules gives it no permission to write across them.

Keeping commands and queries separate needs no message bus, mediator, event-sourced history, separate read database, or general workflow engine.

Chroma holds derived search data outside PostgreSQL. Its [indexing protocol](indexing.md) explains how to keep that data consistent. This special case does not require ordinary database reads to wait for a separate copy of their records to catch up.

<a id="coordination"></a>

## 3. Keep changes consistent

A rule that must remain true after a change is an **invariant**. An **aggregate** groups the related state and behavior responsible for protecting such rules. For example, a Deployment must reject a release change based on an outdated revision.

For example, a `Deployment` owns the rules for:

```text
attach_candidate
set_canary
abort_candidate
promote
rollback_promotion
```

Here, a Deployment selects the pipeline version serving requests. It is not a Docker deployment. Both the API and worker use its domain rules instead of implementing their own versions of promotion or rollback.

A PipelineVersion checks that its saved configuration is valid and immutable. Simpler facts can remain plain immutable values. A **source span**, for example, only identifies where an excerpt came from. Neither it nor a recorded metric needs an elaborate class hierarchy.

### An aggregate does not mean loading every related row

An aggregate defines which rules belong together. It does not mean loading every related database row.

For a collection with one million documents, load the small controlling object and its revision reference. Create, verify, and read the membership records in batches or through database operations over sets of rows. This keeps memory use limited.

The aggregate's main object, called its root, protects the rules. Repository operations handle the larger volume of records.

### Keep database transactions short

Application commands define short PostgreSQL transactions. A transaction groups database changes so they commit together or do not commit at all.

Domain code checks the business rules. Database adapters also reject duplicates, references to the wrong organization or project, and updates based on an outdated revision. These checks use uniqueness constraints, foreign keys, and conditional updates.

Both are needed because two requests can overlap. Alice's command may pass a check, then Bob may change the same record before Alice saves. Database checks prevent her save from breaking a rule or silently replacing his change.

**Admission** means saving that the application has accepted an operation. Its work record, job, retry outcome, and required audit event can all be saved together. The retry outcome tells the application what to return if Alice sends the same request again.

When one transaction owns these records, they can succeed or fail together. There is no need to save them separately and repair partial results later.

### Keep external calls outside long SQL transactions

Record acceptance, finish the database transaction, then call storage or a model. Save completion in another short transaction. Waiting for an external service must not keep a long SQL transaction open.

Workers call the same commands as the API, including when a source sync discovers a new document. A retry reuses the operation's identities. It must not create another domain model or a new source identity each time.

<a id="entry-points"></a>

## 4. Share behavior across entry points

**MCP**, the Model Context Protocol, offers another way to call the same application operations. Pipelines still retrieves documents and produces answers. Access still decides permissions.

Studio calls the application HTTP API through the official generated TypeScript **SDK**, a client library for working with the backend.

Generate those clients from native OpenAPI without choosing a generator package here. **V1 delivers the Rust CLI and small Ory account UI, not full Studio.** Backend work proceeds independently; client compatibility is qualified incrementally against actual contracts. The future Studio follows the same application behavior under [ADR-0055](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md).

Repository skills are guidance for developers and agents. They do not run inside the application.

The MCP integration profile is accepted in [Using Inframeld through MCP](mcp.md).

### Keep domain ownership at every entry point

Pipelines owns answers, receipts, and feedback. Evaluation owns offline comparisons, and Releases selects which version serves requests. Studio may display their information together without taking over any of their writes.

Default setup calls normal commands. A build reports that its version is ready, then a separate Releases command may make it live. [Onboarding](onboarding.md) and [publication modes](pipelines-and-releases.md) explain this flow. Retries and workers follow the same separation.

Access checks the verified caller's current permissions. An adapter cannot accept a client's claimed group list as proof. Model calls use ModelGateway, with provider secrets kept behind the [model connection boundary](model-connections.md).

<a id="maintainer-checks"></a>

## 5. Maintainer checks

| Scenario | Expected outcome |
| --- | --- |
| An HTTP route, MCP tool, and worker perform the same operation | They call the owning application behavior with verified context. |
| A read screen joins two domains | A purpose-built read projection may join data. It does not acquire write ownership. |
| A grant changes while work is queued | The operation performs the current checks required by its owner. |
| An external call times out | No long SQL transaction is held. The owning retry protocol decides what is safe. |
| An index becomes ready | Readiness alone never changes Deployment traffic. |
| A million-row corpus is selected | Use bounded queries and batches. Do not load an entire aggregate into memory. |

### Keeping the code understandable and verifying the boundaries

Use names from the domain, keep related behavior together, return explicit errors, and keep interfaces focused on a clear responsibility.

Use small functions where they improve readability, without a fixed line limit. Explain why consistency and security rules exist in comments and ADRs. Add another DTO only when it translates meaningfully between responsibilities.

Tests should demonstrate business behavior, not just that methods were called. Examples include:

| Scenario | Behavior to verify |
| --- | --- |
| A promotion uses an outdated deployment revision. | The stale promotion is rejected. |
| A materialization has not been published. | It is unavailable for serving. |
| An operation references a resource from another project. | The cross-project reference is denied. |
| A process restarts and retries publication. | Publication is not duplicated. |

The developer manually guards forbidden imports, dependency cycles, and repository organization, following the repository's setup-test policy. Do not add architecture/import-boundary tests, dependency-rule fixtures, or composition-root construction tests. Automated tests verify implemented product behavior, API contracts, and integrations.

Tests of database and search behavior must use real PostgreSQL and the Chroma server shipped with the product. Mocks alone cannot show that real constraints, simultaneous changes, and search operations behave correctly.

<a id="decision-map"></a>

## 6. Decision and reference map

Feature endpoints and rules for simultaneous changes still need implementation and integration tests. Repository structure and dependency rules are reviewed manually under the setup-test policy.

| Decision | Rationale |
| --- | --- |
| [ADR-0001](../adr/ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md) | Use one modular backend with clear domain boundaries. |
| [ADR-0002](../adr/ADR-0002-separate-commands-and-queries-without-a-command-bus-framework.md) | Separate commands and queries without a command-bus framework. |
