# Choose a component and import its type

<a id="choose-a-component-and-import-its-type"></a>

Alice needs to add a project-grant operation. Starting with a generic helper folder would hide who owns the behavior. Start with Access, then the layer, then the component's job. Create a folder only when a real workflow needs it.

<a id="choose-owner-layer-and-role"></a>

## Choose owner, layer and role

Follow domain → layer → component role. Preserve the existing frontend's Next.js conventions. Within the backend, keep authentication and authorization under Access's role folders rather than recreating mixed capability folders.

| Layer | Role folders, created only when needed |
| --- | --- |
| Domain | `entities`, `value_objects`, `enums`, `policy_inputs`, `policies`, `errors`, `validation` |
| Application | `services`, `protocols`, `commands`, `queries`, `dtos`, `value_objects`, `enums`, `errors` |
| HTTP | `routes`, `dependencies`, `requests`, `responses`, `middleware`, `handlers`, `mappers`, `builders`, `openapi`, `definitions`, `types`, `validation` |
| Infrastructure | `readers`, `repositories`, `mappers`, `verifiers`, `revokers`, `rows`, `settings`, `resources`, `migrations`, `logging`, `diagnostics`, `timing`, `errors`, `types` |

| Component | Required name and responsibility |
| --- | --- |
| Business orchestration | Instantiated `*Service` coordinates the complete workflow through injected protocols. |
| Public operation | Capability-named `Protocol`, such as `HumanSessionAuthenticator` or `ActionAuthorizer`. |
| Specific I/O capability | Focused protocol, such as `BrowserSessionVerifier` or `HumanIdentityLinkReader`. |
| Aggregate repository | Specific application protocol, such as `ProjectMembershipRepository`. Load existing aggregates and persist supported transitions without committing. |
| Infrastructure adapter | Technology-prefixed class, such as `PostgresHumanIdentityLinkReader`, in its role folder. |
| FastAPI dependency | `*Dependency` extracts inputs and invokes the operation. |
| Route registration | `*_routes.py` translates HTTP input/output. |
| Feature HTTP mapping | Static `*Mapper` in `mappers/*_mapper.py`, converting Command input and responses without I/O. |
| ASGI middleware | `*Middleware` in `*_middleware.py`, wrapping request lifecycle. |
| Change input | `*Command` in `commands/*_command.py`, never `CommandDTO`. |
| Read input | `*Query` in `queries/*_query.py`, never `QueryDTO`. |
| Other transfer record | `*DTO` in `dtos/*_dto.py`, including results, projections and caller/operation contexts. |
| Dedicated policy input | `*PolicyInput` in `policy_inputs/*_policy_input.py`. |
| HTTP model | Pydantic `*Request`/`*Response`, preserving published schema names. |
| Persistence mapping | `*Row` in `infrastructure/rows`. |
| Shared persistence conversion | Technology-prefixed static `*Mapper` in `infrastructure/mappers`, without I/O or authorization. |
| Configuration | `*Settings` in `infrastructure/settings`, aggregated by bootstrap. |
| Pure business decision | `*Policy` in `policies/*_policy.py`, with pure static methods. |

For example, `AssignProjectUseOnlyGrantCommand` belongs in `application/commands/` and `GetProjectQuery` in `application/queries/`. The first is implemented. The latter is a naming example, not evidence of a delivered read. Results and metadata such as `CommandContextDTO` retain DTO. Technology-prefixed aggregate adapters belong in `infrastructure/repositories`.

<a id="give-each-public-type-a-home"></a>

## Give each public type a home

Use one primary public type per production module. Entities, identifiers, enums, commands, queries and policy inputs get their own type-named files. Cohesive exception families, private helpers, constants and framework type aliases may stay grouped.

Import directly from the defining module. For example, import `ValueValidation` from its defining module and call `ValueValidation.require_uuid(value)`. Do not introduce a module alias as another namespace for that utility. Standard-library and SDK module imports remain valid where appropriate.

After an internal move, migrate callers and remove the obsolete layout without compatibility aliases. Bootstrap records such as `AccessComponents` and `ApplicationResources` keep purpose-specific names. They are not application DTOs.

<a id="review-the-proposed-component"></a>

## Review the proposed component

Before generating a component, identify owner, layer, role, destination, name, declaration style and behavioral contract. Confirm that directory and name agree and that conversions happen at the appropriate boundary.

Do not introduce an aggregate, repository or abstraction merely to demonstrate a pattern. If a proposed mapper needs current permission checks or database I/O, that work belongs to the application workflow and its injected capabilities. See [service boundaries](../../inframeld-application-contracts/references/components-and-services.md).

<a id="worked-example-add-the-grant-operation"></a>

## Worked example: add the grant operation

**Situation.** Alice needs to give Bob use-only permission on Support. Treat this as a component-design exercise using the operation that now exists. Access owns permission changes. The implementation needs a business operation, a domain transition, persistence and an HTTP boundary.

**Decision and placement.** Choose the owner first, then the layer and job. The following is a selected tree of existing files under `apps/backend/src/inframeld_backend/`, not a proposal to create them again:

```text
access/
  domain/entities/project_membership.py
  domain/policies/project_grant_delegation_policy.py
  application/commands/assign_project_use_only_grant_command.py
  application/protocols/project_grant_changer.py
  application/protocols/project_membership_repository.py
  application/services/project_grant_change_service.py
  http/requests/project_use_only_grant_request.py
  http/responses/project_use_only_grant_response.py
  http/mappers/project_use_only_grant_mapper.py
  http/routes/project_grant_routes.py
  infrastructure/repositories/postgres_project_membership_repository.py
bootstrap/
  project_grant_composition.py
```

The public `ProjectGrantChanger` capability belongs in application protocols because callers need its behavior without knowing the database. Its `ProjectGrantChangeService` implementation belongs in services because it sequences the operation. The membership belongs in domain entities because it owns a cohesive collection and the rules for changing it. Its specific repository port describes loading and saving that aggregate. The PostgreSQL implementation belongs in infrastructure repositories because it performs database work.

A flat Command carries the requested change. The HTTP mapper converts validated external values, while routes invoke the operation and serialize its result. Bootstrap selects concrete adapters and supplies their shared session. Do not construct a database adapter inside the service or add a repository to the route merely because HTTP initiated the request.

**Code and walkthrough.** Bootstrap's complete composition function demonstrates direct imports, explicit assembly and session lifetime:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/bootstrap/project_grant_composition.py](../../../../apps/backend/src/inframeld_backend/bootstrap/project_grant_composition.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.services.project_grant_authorization_service import (
    ProjectGrantAuthorizationService,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

@asynccontextmanager
async def open_project_grant_change(
    database: Database, fingerprints: ProjectGrantChangeFingerprintService
) -> AsyncGenerator[ProjectGrantChanger]:
    """Close one request-local session after the application operation owns its transaction."""
    async with database.session() as session:
        yield ProjectGrantChangeService(
            transactions=SqlAlchemyTransactionManager(session),
            authorizer=ProjectGrantAuthorizationService(
                PostgresProjectGrantChangeFactsReader(session)
            ),
            idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            memberships=PostgresProjectMembershipRepository(
                session, PostgresAuditEventWriter(session)
            ),
            fingerprints=fingerprints,
        )
```

The constructor lists the operation's dependencies instead of hiding them in a generic work object. All database collaborators receive this session. The service opens its transaction, and this context closes the session after the operation. The concrete fingerprint helper is supplied rather than recreated with a different key or request meaning.

**Failures and alternatives.** A repository does not verify the browser credential. Authentication and applicable CSRF checks finish before the route opens this composition context. If the service fails, its transaction owns rollback. Assembly owns resource lifetime, not permission or business decisions. See [the complete service example](services-and-use-cases.md) before suggesting this shape for another write.

<a id="worked-example-read-facts-without-inventing-an-aggregate"></a>

## Worked example: read facts without inventing an aggregate

**Situation.** An authorizer needs current account, project and exact-grant facts. It needs an observation for a decision, not a mutable object to save.

**Decision and placement.** The existing `ProjectActionFactsReader` application protocol, `PostgresProjectActionFactsReader` infrastructure reader and `ProjectActionFactsDTO` result express that need. A typed projection is a named view of selected data. It need not contain every record in an aggregate.

Read [the reader implementation](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_project_action_facts_reader.py) for its typed query and conversion. The [typed read example](protocols-and-persistence.md#worked-example-read-a-typed-projection) shows a smaller implemented projection with code. A facts DTO does not decide access. The application authorizer passes current facts to the appropriate policy.

**Failures and alternatives.** This authorization reader uses the caller's transaction. An independent authentication reader has a different lifetime. Preserve each capability's actual contract. Do not add a write reservation, mutable aggregate or generic repository to make reads resemble writes. `GetProjectQuery` remains a naming illustration, not an implemented endpoint.

<a id="component-conventions"></a>

<a id="finding-a-component-in-the-implemented-backend"></a>

### Finding a component in the implemented backend

Follow **domain → layer → component role**. First choose the owner, then the layer, then the job the component performs. To follow a business workflow, open its application service. To inspect a collaborator's contract, open its protocol. Authentication and authorization share these role folders inside Access.

The layout below shows the main components under `apps/backend/src/inframeld_backend/`. Individual row mappings and some shared adapters are abbreviated. Create a role folder only when implemented code needs it.

```text
inframeld_backend/
├── main.py
├── migrate.py
├── bootstrap/                         # construction, assembly, settings, lifecycle
│   ├── application_factory.py
│   ├── application_settings.py
│   ├── access_composition.py
│   ├── project_grant_composition.py
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
│   │   ├── commands/assign_project_use_only_grant_command.py
│   │   ├── services/
│   │   │   ├── human_session_authentication_service.py
│   │   │   ├── human_access_token_authentication_service.py
│   │   │   ├── unavailable_human_session_authentication_service.py
│   │   │   └── action_authorization_service.py
│   │   ├── protocols/
│   │   │   ├── human_session_authenticator.py
│   │   │   ├── human_access_token_authenticator.py
│   │   │   ├── human_access_token_verifier.py
│   │   │   ├── human_identity_verifier.py
│   │   │   ├── action_authorizer.py
│   │   │   ├── browser_session_verifier.py
│   │   │   ├── human_identity_link_reader.py
│   │   │   └── project_action_facts_reader.py
│   │   ├── dtos/
│   │   │   ├── access_context_dto.py
│   │   │   ├── verified_human_identity_dto.py
│   │   │   ├── project_action_target_dto.py
│   │   │   └── project_action_facts_dto.py
│   │   └── value_objects/
│   │       ├── browser_session_credential.py
│   │       └── human_access_token_credential.py
│   ├── http/
│   │   ├── routes/                    # current_session_routes, project_grant_routes
│   │   ├── dependencies/              # HumanSessionDependency, CSRFProtectionDependency
│   │   ├── mappers/project_use_only_grant_mapper.py
│   │   ├── openapi/human_authentication_responses.py
│   │   └── responses/                 # CurrentSessionResponse, ProjectUseOnlyGrantResponse
│   └── infrastructure/
│       ├── readers/                   # PostgresHumanIdentityLinkReader, project facts reader
│       ├── mappers/postgres_human_credential_state_mapper.py
│       ├── revokers/hydra_human_oauth_credential_revoker.py
│       ├── verifiers/
│       │   ├── kratos_browser_session_verifier.py
│       │   ├── hydra_access_token_verifier.py
│       │   └── kratos_human_identity_verifier.py
│       ├── settings/                   # KratosSettings, HydraSettings, CSRFSettings
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

<a id="component-roles-and-naming"></a>

### Component roles and naming

Use one primary public type per production module, with a matching snake-case filename. Entities, IDs, enums, and policy inputs have separate defining modules. Cohesive exception families, private helpers, constants, and framework type aliases may remain grouped. Import from the defining module. Do not retain compatibility aliases after an internal move.

| Role | Naming and example | Responsibility |
| --- | --- | --- |
| Application operation | Capability-named protocol: `HumanSessionAuthenticator`, `ActionAuthorizer` | Specify public inputs, results, failures, and ownership independently of HTTP and vendors. |
| Application service | `*Service`: `HumanSessionAuthenticationService` | Coordinate the complete workflow through injected protocols. |
| I/O capability | Specific protocol: `BrowserSessionVerifier`, `ProjectActionFactsReader` | State the external capability the application requires. |
| Provider revocation | Specific protocol: `HumanOAuthCredentialRevoker`, with `HydraHumanOAuthCredentialRevoker` in `infrastructure/revokers` | Revoke a trusted provider scope and report confirmation, rejection or uncertainty. |
| Aggregate repository | Specific protocol: `ProjectMembershipRepository`, with `PostgresProjectMembershipRepository` in `infrastructure/repositories` | Load an existing aggregate and persist supported changes and audit in the caller's transaction. |
| Entity | `Principal` in `entities/principal.py` | Hold account state with stable identity. Equality follows its ID. |
| Value object | `PrincipalId`, `IdentitySubject`, `BrowserSessionCredential` in `value_objects` | Give a value its meaning and enforce its invariants. |
| Enum | `PrincipalStatus` in `enums/principal_status.py` | Define a closed vocabulary. |
| CQRS command input | `*Command` in `commands/*_command.py` | Describe the change to request, such as `AssignProjectUseOnlyGrantCommand`. |
| CQRS query input | `*Query` in `queries/*_query.py` | Describe the read to request, such as `GetProjectQuery`. |
| Other application DTO | `*DTO` in `dtos/*_dto.py` | Carry results, read projections, or caller/operation context. |
| Dedicated policy input | `*PolicyInput` in `policy_inputs/*_policy_input.py` | Supply the values a domain policy needs for its decision. |
| Policy | `*Policy` in `policies/*_policy.py` | Make a pure decision through static methods with explicit inputs. |
| Adapter | Technology-prefixed `PostgresHumanIdentityLinkReader`, `KratosBrowserSessionVerifier` | Perform I/O and convert external values at the boundary. |
| HTTP dependency | `*Dependency` | Extract request inputs and invoke an application operation. |
| Routes | `*_routes.py` | Register endpoints and translate their inputs and outputs. |
| Feature HTTP mapper | Static `*Mapper` class in `mappers/*_mapper.py` | Convert validated HTTP input to a Command and application results to the published response. Perform no I/O. |
| HTTP model | `*Request` / `*Response` | Validate or serialize the wire contract using Pydantic. |
| Middleware | `*Middleware` in `*_middleware.py` | Wrap the ASGI request lifecycle. |
| ORM mapping | `*Row` in `infrastructure/rows` | Map persisted fields using typed constructors and expressions. |
| Shared persistence conversion | Technology-prefixed static `*Mapper` in `infrastructure/mappers` | Convert database projections into application/domain values when several adapters share that conversion. Perform no I/O or authorization. |
| Settings | `*Settings` in `infrastructure/settings` | Validate resource configuration. Bootstrap aggregates it. |
| Bootstrap assembly | `AccessComponents`, `ApplicationResources` | Group constructed collaborators and owned resources. These are not application DTOs. |

Existing published HTTP names such as `ProblemDetails` and `ValidationIssue` are preserved, including their OpenAPI descriptions. New HTTP models use Request/Response naming. CQRS command and query inputs end in `Command` and `Query`, without `DTO`. Other application transfer records use the uppercase `DTO` suffix, including command/query results, read projections, and caller/operation metadata.

`AssignProjectUseOnlyGrantCommand` is implemented under Access's `application/commands/` folder and describes the supported grant change. `GetProjectQuery` remains a naming example for a future read that benefits from a named input. Create role folders with the first real workflow that needs them. Query results can still be DTOs, and `CommandContextDTO` remains metadata rather than a command input.

This follows the CQRS distinction between a request to change state and a request to read it. Microsoft describes a command as a specialized DTO and illustrates a purpose-specific name such as `CreateOrderCommand`. Inframeld uses the more specific `Command` and `Query` suffixes for these input roles. They need no DTO base class or command bus. The agreed nominal `Command` base supplies classification only. See [Microsoft's command definition](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/microservice-application-layer-implementation-web-api#the-command-class) and [CQRS overview](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs).

[ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md) selects a nominal `Command` base in `shared/application/commands/command.py` and the field-based `ProjectCommand` Protocol in `shared/application/protocols/project_command.py`. A concrete project Command explicitly inherits both and declares `project_id: ProjectId` itself. The interface provides neither stored fields nor execution. Commands for organization-wide changes need no project field. A Protocol cannot extend a nominal class, so the two bases meet on the concrete Command.

Strict Pyright rejects the wrong field type and an attempt to instantiate an explicit implementation missing `project_id`. This does not guarantee an error at the incomplete class declaration, perform runtime field validation or express read-only access through the Protocol. Concrete Commands remain frozen, slotted dataclasses. These required-field contracts and nominal classification are narrow exceptions to the normal preference for behavioral interfaces.

Keep execution in application services behind capability-named protocols. A command or query input may reject invalid values or inconsistent combinations of its own fields without I/O. It cannot establish current permission, resource existence, or a match with the current stored revision. Preserve those checks in their owning workflows. Direct typed parameters remain valid when a separate input record would add no useful meaning.

A FastAPI dependency and ASGI middleware have different lifetimes. FastAPI invokes `HumanSessionDependency` for the route that declares it. `RequestContextMiddleware` wraps requests at the ASGI boundary. The cookie workflow belongs to `HumanSessionAuthenticationService`, and the human bearer workflow belongs to `HumanAccessTokenAuthenticationService`. The dependency chooses one of them before provider verification.

<a id="status-and-sources"></a>

## Status and sources

These are mandatory backend conventions. They do not authorize edits or imply that every example component exists. Read the relevant workflow before claiming implementation.

- [Canonical component conventions](#component-conventions) own roles, placement and naming.
- [Static utilities and mappers](static-utilities-and-mappers.md) explain pure helper calls. [Values and records](values-and-records.md) explain declaration choices.
