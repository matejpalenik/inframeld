# Choose a component and import its type

Alice needs to add a project-grant operation. Starting with a generic helper folder would hide who owns the behavior. Start with Access, then the layer, then the component's job. Create a folder only when a real workflow needs it.

## Contents

- [Choose owner, layer and role](#choose-owner-layer-and-role)
- [Give each public type a home](#give-each-public-type-a-home)
- [Review the proposed component](#review-the-proposed-component)
- [Worked example: add the grant operation](#worked-example-add-the-grant-operation)
- [Worked example: read facts without inventing an aggregate](#worked-example-read-facts-without-inventing-an-aggregate)
- [Status and sources](#status-and-sources)

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

## Give each public type a home

Use one primary public type per production module. Entities, identifiers, enums, commands, queries and policy inputs get their own type-named files. Cohesive exception families, private helpers, constants and framework type aliases may stay grouped.

Import directly from the defining module. For example, import `ValueValidation` from its defining module and call `ValueValidation.require_uuid(value)`. Do not introduce a module alias as another namespace for that utility. Standard-library and SDK module imports remain valid where appropriate.

After an internal move, migrate callers and remove the obsolete layout without compatibility aliases. Bootstrap records such as `AccessComponents` and `ApplicationResources` keep purpose-specific names. They are not application DTOs.

## Review the proposed component

Before generating a component, identify owner, layer, role, destination, name, declaration style and behavioral contract. Confirm that directory and name agree and that conversions happen at the appropriate boundary.

Do not introduce an aggregate, repository or abstraction merely to demonstrate a pattern. If a proposed mapper needs current permission checks or database I/O, that work belongs to the application workflow and its injected capabilities. See [service boundaries](../../inframeld-application-contracts/references/components-and-services.md).

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

## Worked example: read facts without inventing an aggregate

**Situation.** An authorizer needs current account, project and exact-grant facts. It needs an observation for a decision, not a mutable object to save.

**Decision and placement.** The existing `ProjectActionFactsReader` application protocol, `PostgresProjectActionFactsReader` infrastructure reader and `ProjectActionFactsDTO` result express that need. A typed projection is a named view of selected data. It need not contain every record in an aggregate.

Read [the reader implementation](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_project_action_facts_reader.py) for its typed query and conversion. The [typed read example](protocols-and-persistence.md#worked-example-read-a-typed-projection) shows a smaller implemented projection with code. A facts DTO does not decide access. The application authorizer passes current facts to the appropriate policy.

**Failures and alternatives.** This authorization reader uses the caller's transaction. An independent authentication reader has a different lifetime. Preserve each capability's actual contract. Do not add a write reservation, mutable aggregate or generic repository to make reads resemble writes. `GetProjectQuery` remains a naming illustration, not an implemented endpoint.

## Status and sources

These are mandatory backend conventions. They do not authorize edits or imply that every example component exists. Read the relevant workflow before claiming implementation.

- [Canonical component conventions](../../../../docs/development/application-structure.md#component-conventions) own roles, placement and naming.
- [Static utilities and mappers](static-utilities-and-mappers.md) explain pure helper calls. [Values and records](values-and-records.md) explain declaration choices.
