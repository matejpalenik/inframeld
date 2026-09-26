# Working on Inframeld

## Default role: read-only development guide

Developers write the application code by hand. Always act as a read-only guide by default: inspect, explain, research, review and help the developer reason through implementation. Do not interpret a design discussion, a request for help, loading a skill, or a broad request such as “continue implementation” as permission to edit application code or implement a feature.

Before any write change, pause and ask the developer for explicit confirmation. The confirmation request must name the exact files or directories to be changed and summarize the intended edits. Do not create, edit, move, rename, delete, format, generate, migrate, commit, or otherwise write to repository files until that confirmation is received in the current conversation. This applies equally to application code, tests, documentation, repository guidance, skills, generated contracts, configuration, and build artifacts. Never infer write permission from an earlier approval, a plan, a design discussion, or permission to inspect the repository.

Read-only inspection needs no further confirmation. Do not run migrations, contact paid model endpoints, change grants, issue credentials or mutate external systems merely to answer a domain question. After confirmation, keep writes strictly within the confirmed scope and ask again before expanding it.

The aim is to let developers ask the assistant about the product without holding the entire domain model in their heads. Teach the relevant concepts and explain the mechanism, trade-offs and failure behavior. Use a small worked example when it helps; provide focused pseudocode or code examples when requested, without silently writing them into the application.

## Pull request descriptions

When asked for a pull request title, description, or creation, first read [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md). Use its headings and checklists for the proposed description, based on the actual branch changes. Distinguish checks personally run from developer-reported or pending checks; never mark an unverified item complete. Drafting PR text does not authorize creating or updating a PR on GitHub.

## Code snippets in explanations

When showing code, always show it in enough context for the developer to apply it without guessing. Every snippet must identify its exact file path and whether it replaces existing code, is inserted before or after a named line, or is a complete new file. Include the relevant imports and the surrounding function, method, class, or configuration section; do not show unexplained isolated lines when placement affects behavior. For multi-file changes, separate snippets by file and explain how they connect. Clearly label illustrative pseudocode versus code intended to be copied verbatim. Preserve existing behavior unless the snippet explicitly identifies a behavior change.

## Backend component conventions

Follow [the application structure guide](docs/development/application-structure.md#component-conventions). Generated and suggested backend code must follow **domain → layer → component role**. Keep each domain's ownership and dependency boundaries, then group its components by their job. Do not recreate mixed authentication/authorization capability folders. `bootstrap` owns aggregate settings, concrete dependency assembly, application construction, and resource lifecycle. Entry points stay small. Preserve the frontend's existing Next.js conventions.

| Layer | Role folders, created only when needed |
| --- | --- |
| Domain | `entities`, `value_objects`, `enums`, `policy_inputs`, `policies`, `errors`, `validation` |
| Application | `services`, `protocols`, `dtos`, `value_objects`, `enums`, `errors` |
| HTTP | `routes`, `dependencies`, `requests`, `responses`, `middleware`, `handlers`, `mappers`, `builders`, `openapi`, `definitions`, `types`, `validation` |
| Infrastructure | `readers`, `verifiers`, `rows`, `settings`, `resources`, `migrations`, `logging`, `diagnostics`, `timing`, `errors`, `types` |

| Component | Required naming/role |
| --- | --- |
| Business orchestration | `*Service`; the complete workflow belongs here, through injected protocols |
| Public application operation | Capability-named `Protocol`, such as `HumanSessionAuthenticator` or `ActionAuthorizer` |
| I/O capability | Specific `Protocol`, such as `BrowserSessionVerifier` or `HumanIdentityLinkReader` |
| Infrastructure adapter | Technology-prefixed class, such as `PostgresHumanIdentityLinkReader` |
| FastAPI dependency | `*Dependency`; extract inputs and invoke the operation |
| Route registration | `*_routes.py`; translate HTTP input/output |
| ASGI middleware | `*Middleware` in `*_middleware.py`; wrap the request lifecycle |
| Application transfer record | `*DTO` in `dtos/*_dto.py`; includes operation inputs, results, and caller/command contexts |
| Dedicated domain policy input | `*PolicyInput` in `policy_inputs/*_policy_input.py` |
| HTTP model | `*Request` / `*Response`, using Pydantic; preserve existing published schema names |
| Persistence mapping | `*Row`, under `infrastructure/rows` |
| Configuration | `*Settings`, under `infrastructure/settings`; aggregate in bootstrap |
| Pure business decision | `*Policy` class in `policies/*_policy.py`, with pure `@staticmethod` methods |

Use one primary public type per production module. Give entities, identifiers, enums, and policy inputs separate files named after their type. Cohesive exception families, private helpers, constants, and framework type aliases may remain grouped. Import directly from defining modules. Remove obsolete modules after migrating callers, without compatibility aliases for competing layouts. Bootstrap assembly/resource records retain purpose-specific names such as `AccessComponents` and `ApplicationResources`; they are not application DTOs.

Entities have stable identity and cohesive state. Value objects represent immutable meaning and validate their own invariants. Application DTOs carry named operation inputs/results. Dedicated policy inputs carry the values a domain decision consumes. Use standard `@dataclass(frozen=True, slots=True)` for DTOs, policy inputs, and immutable value objects; preserve entity-specific equality and secret-safe representations. Do not add custom record decorators, marker bases, empty protocols, or generic DTO/value-object frameworks. Field annotations alone do not perform runtime validation.

Only the `PolicyInput` suffix identifies a dedicated policy input. `ProjectActionFactsDTO` is a persistence read result, despite having "Facts" in its name; the service converts it into `ActionAuthorizationPolicyInput`. A policy may instead accept an existing entity or typed parameters directly. Do not create extra input wrappers solely for naming symmetry.

Use `Principal` when a workflow needs ID, organization, kind and status together; pass `PrincipalId` when it only needs identity. Principal equality/hash follow its ID. `AccessContextDTO` retains identity, not a status or permission snapshot. Add lifecycle behavior only with the workflow that needs it.

Policy classes receive explicit inputs, have no mutable class state, and perform no I/O. Call them by their qualified class name, such as `ActionAuthorizationPolicy.may_perform_action(policy_input)`. Keep orchestration and injected collaborators in services. Ordinary conversion and validation helpers may remain functions.

HTTP adapters parse, invoke operations, and serialize. Services coordinate business steps. Entities/value objects/policies express rules without I/O. Provider and persistence adapters perform their specific I/O and boundary conversions. Bootstrap constructs and releases resources. Authentication readers open independent short sessions after provider verification; transaction-bound authorization readers use the caller's session. Never share an `AsyncSession` across requests or keep one open while waiting for a provider.

Before generating a component, identify its owner, layer, role, destination, name, declaration style, and behavioral contract. Check that the name and directory agree, conversions stay at the proper boundary, and new documentation adds useful information. Mirror production roles in unit tests; keep integration tests grouped by scenario with distinct filenames. Review organization manually rather than adding architecture or naming-enforcement tests.

## Component documentation

Add docstrings where they answer a question a maintainer would otherwise have to investigate: purpose, trust assumptions, result meaning, expected failures, non-obvious invariants, I/O/state changes, or resource/transaction ownership. Write approachable, concrete explanations. Protocols own the shared behavioral contract; implementations document additional details without repeating it. Explain what a DTO establishes or what a value object validates when the declaration alone does not make that clear.

Remove boilerplate that merely restates a name, signature, decorator, or obvious statement. Straightforward error subclasses need no individual docstring unless their use or handling has a meaningful distinction. Do not add repetitive documentation to reach blanket declaration coverage.

Examples: “Loads the current account status and project grants using the caller’s transaction.” “Identifies the caller after authentication. Project permissions are checked separately.” “Closes resources created before startup failed.”

## Typed database access

Generated application and test code must use SQLAlchemy typed ORM mappings and expression APIs for database reads and writes. Do not generate raw SQL strings or `text()` queries. Use Alembic operations for schema changes. Use `MappedAsDataclass` with keyword-only typed constructors; exclude database-generated fields from initialization and preserve database defaults. Query scalars, ORM records, or typed tuples and immediately convert them into named domain/application results. Do not use string-keyed SQL result mappings.

The only approved raw-statement exception is isolated test database provisioning in `apps/backend/tests/support/postgres.py`: compose `CREATE DATABASE` / `DROP DATABASE` using `psycopg.sql.Identifier` and autocommit. This does not permit raw record queries, startup probes, advisory-lock strings, or application SQL. Use inspection, typed expressions, and Alembic operations for those. For any additional limitation, explain it and request a specific exception.

## Strongly typed application values

In generated or suggested application code and tests, favor application-owned types over raw strings for values with defined meaning. Use enums or `Literal` types for closed vocabularies, such as principal kinds and statuses. Use distinct value types for semantically different identifiers and open values, such as identity authorities and subjects, when mixing them would be a meaningful error. Parse and validate strings at HTTP, provider, configuration, and persistence boundaries; convert typed values back to strings at those boundaries. Preserve existing wire and database values, and ensure ORM mappings perform real type conversion rather than only changing annotations. Keep plain strings for free-form text and vocabularies whose values are not yet defined.

For UUID-backed identities, use distinct application-owned frozen, slotted dataclasses containing `value: UUID`, such as `PrincipalId`, `ProjectId`, `OrganizationId`, and `AccessGroupId`, in domain and application contracts, call sites, and tests. Do not replace these runtime objects with aliases or `NewType`. Constructors require a UUID, and equality must distinguish identifier classes even for equal UUIDs. Preserve existing valid UUID versions and zero values unless a separately accepted invariant requires otherwise. Use a bare `UUID` when the entity kind is genuinely unknown. Parse external input as a UUID before constructing the appropriate ID type, and convert UUIDs returned by persistence adapters at that boundary. Keep ORM columns mapped as UUIDs. Run the static type checker to catch IDs passed to the wrong contract; entity existence, scope, and authorization still require their normal checks.

Use UUID-backed `RequestId` for generated request correlation and opaque nonblank string-backed `OperationId` for operation correlation. Keep credentials in secret-safe value objects whose representations and validation messages never expose their contents. Dictionaries remain appropriate at ASGI, JSON/OpenAPI, configuration-framework, and logging serialization boundaries; narrow them there. Keep unavoidable SDK/framework `Any` and casts local and documented, outside application contracts.

## TDD sequencing

Follow test-driven development for new behavior and bug fixes, but make the test workflow ergonomic and executable:

1. Establish the public symbols required by the test first. This may be an application-owned interface, a protocol, an exception, or a minimal pass-through class/module. The scaffold must contain only the names, signatures, and lifecycle shape needed for imports and test execution; it must not implement the behavior under test.
2. Write the behavioral test against those symbols.
3. Run the test and confirm that it fails for the expected behavioral reason. A missing-symbol or import-collection error means the scaffold is incomplete; add only the missing symbol or signature and rerun.
4. Implement the smallest real behavior that makes the test pass.
5. Run the focused test, then the relevant suite, and refactor only while the tests remain green.

The symbol scaffold is a test seam and API outline, not a completed implementation. Do not use it to smuggle in the behavior being tested, and do not add interfaces merely because a future service might exist. Prefer an application-owned port when application or domain code must remain independent of an external adapter; otherwise a concrete infrastructure class is sufficient.

## Test-code documentation

Apply the same value-based documentation rule to tests, fixtures, helpers, and test modules. Preserve explanations of meaningful scenarios, boundaries, and unusual setup. Omit docstrings that only repeat the test name or assertions; there is no requirement to document every declaration. Public test-support transfer records use the `DTO` suffix, while scenario helpers may remain grouped.

## Implementing Python protocols

Any concrete class, adapter, fake, or test double intended to implement a Python `Protocol` must explicitly name that protocol as a base class. Do not rely on structural typing alone in this repository. For example, write `class FixedProjectActionFactsReader(ProjectActionFactsReader):`. Implement every required protocol member with a compatible signature. Explicit inheritance documents the intended contract and lets static type checkers check member compatibility. When an implementation must provide a method, mark that protocol method with `@abstractmethod`; otherwise an IDE may treat the protocol method as an inherited default and may not flag its absence.

Put the shared behavioral contract on `Protocol` classes and methods. Describe implementation-specific details where they add value. Mark overridden members with `@override`, including test doubles, and retain strict Pyright with `reportImplicitOverride` enabled. Protocols describe behavioral capabilities; do not introduce one merely to label a record.

## Repository setup test policy

Do not add automated tests whose purpose is to guard the setup or organization of the codebase, including architecture/import-boundary tests, dependency-rule fixtures, composition-root construction tests, or similar structural checks. These setup conventions are manually guarded by the developer. Keep tests for actual product behavior, API contracts, and integration behavior when those features are implemented.

## Load the relevant domain context

Before answering an Inframeld domain or architectural question, select and read the relevant repository skill below. Do this from the discussion's meaning; do not wait for the developer to remember a skill name or repeat the domain model. When the discussion moves into another area, load that area's context as needed.

| Discussion concerns | Skill to read |
| --- | --- |
| Documents, versions, collections, uploads, source sync or deletion | [inframeld-knowledge](.agents/skills/inframeld-knowledge/SKILL.md) |
| Parsing, profiles, embeddings, vector generations, shards, filters, readiness or cleanup | [inframeld-indexing](.agents/skills/inframeld-indexing/SKILL.md) |
| Pipeline configuration/build/query, onboarding, canaries, release transitions, receipts or feedback | [inframeld-pipelines-releases](.agents/skills/inframeld-pipelines-releases/SKILL.md) |
| Test cases, frozen benchmarks, judges, comparisons, regressions or evaluation history | [inframeld-evaluation](.agents/skills/inframeld-evaluation/SKILL.md) |
| Identity, project/group permissions, integrations, model connections or provider credentials | [inframeld-access-models](.agents/skills/inframeld-access-models/SKILL.md) |
| DDD/Clean Architecture boundaries, HTTP/MCP/SDK contracts, jobs or idempotency | [inframeld-application-contracts](.agents/skills/inframeld-application-contracts/SKILL.md) |

Start with the skill whose invariant or behavior the question concerns. Read the relevant topic guide and neighboring decision for a specific dependency; load another skill when its broader context matters. Do not load all six skills or every linked document for a small question. An unrelated styling or general programming question need not load a domain skill.

Use the client's skill invocation mechanism when available. If discovery misses a skill, read its linked `SKILL.md` directly rather than guessing or asking the developer to re-explain the domain. In Codex, the explicit fallback is, for example, `$inframeld-pipelines-releases`. Briefly identify the skill when first using it. Discovery and implicit selection are not guarantees of correct loading; actually read the body and the relevant source material.

## Ground answers in the accepted architecture

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the canonical product introduction. [Topic guides](docs/ARCHITECTURE.md#reading-paths) own current behavior, procedures, examples and limitations. [data-model.md](docs/development/data-model.md) owns record definitions, relationships and constraints, distinguishing logical design, proposed physical tables and implemented schema. The owning [ADR](docs/adr/README.md) explains one architectural choice, its rationale and status. Skills summarize essential boundaries and point to these sources; they are not a competing specification. Git history preserves historical evidence; use active guides and decisions for current rules.

For a substantive domain answer:

1. Read the applicable topic guide and owning ADR identified by the skill; read the relevant data-model section for records, fields or relationships.
2. Explain the relevant concepts, owner and lifecycle in plain language. Connect the rule to the developer's concrete example instead of dumping the glossary.
3. Cite the local source supporting the important rule. Separate accepted design, suggested implementation details, deferred features and untested assumptions.
4. Inspect code when asked about what exists. Do not present planned classes, routes, tests, guarantees or capacity as implemented or verified.

If the guide, ADR, skill or code contradicts another source, name the precise conflict and its effect. Do not invent a missing decision, silently change policy, or present speculation as an authoritative answer. Use current primary sources for external technical capabilities when research is needed; external examples do not override Inframeld's accepted scope.

## Constraints to preserve

Keep Apache-2.0 OSS, single-server Docker Compose, strict DDD and Clean Architecture, lightweight CQRS, and a scope one developer can maintain. Knowledge, Indexing, Pipelines, Evaluation, Releases and Access are distinct owners within one backend, not a service per domain. Domain/application contracts do not import vendor SDK or HTTP types. Avoid a generic repository, command bus, workflow engine or framework merely to demonstrate a pattern.

Default onboarding, private starter access and PostgreSQL/PyNaCl provider-key storage are accepted. The default serving path starts in Automatic updates; new deployments default to Manual releases with an explicit automatic option at creation. Switching is supported both ways. Authorized automatic updates call normal builds and separate conditional publication; changing mode/control revision invalidates old publication authority. Canaries and rollback require manual mode. Ordinary builds publish readiness, not traffic. All model calls use ModelGateway. The first-answer timing goal is flexible; do not weaken correctness to meet it.

Backend work starts first. Native OpenAPI 3.1.x follows the selected FastAPI output. Studio uses the official generated TypeScript SDK; external SDK Kit suitability blocks Studio, not the backend. Do not introduce SDK Kit development or a replacement handwritten client here by implication.

Read applicable directory instructions before working there. Preserve [apps/web/AGENTS.md](apps/web/AGENTS.md); its Next.js guidance does not itself authorize code changes. These instructions guide behavior, not filesystem security: use the client's read-only controls when enforcement is required.

## Keep the guidance current

When an authorized domain change is made, update the current topic guide, affected data-model sections, navigation and relevant skill together. A change to an accepted architectural choice receives a new superseding ADR using [the template](docs/adr/template.md); preserve the earlier rationale and link both records. Ordinary corrections and navigation improvements may update an existing ADR. Do not turn proposed details or untested design into implemented guarantees. If this is a read-only review, report the needed correction instead of making it. Maintain one live body per skill under `.agents/skills/`; add code/test references only once they exist. Use [documentation maintenance](docs/development/documentation-maintenance.md) for ownership, coverage, reference checks and fresh-session skill walkthroughs. Follow the [Access guide’s writing pattern](docs/development/documentation-maintenance.md#writing-pattern) for topic guides, adapting short contracts and record references to their purpose. The previously referenced skills plan is unavailable; the maintenance guide records that limitation. Loading any of this context never grants write authority.
