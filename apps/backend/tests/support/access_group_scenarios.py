"""Compose real group creation with controlled incoming identity evidence."""

from functools import partial
from uuid import uuid4

from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.services.access_group_creation_fingerprint_service import (
    AccessGroupCreationFingerprintService,
)
from inframeld_backend.access.application.services.access_group_creation_service import (
    AccessGroupCreationService,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.access.http.routes.access_group_routes import create_access_group_router
from inframeld_backend.access.infrastructure.readers.postgres_access_group_creation_facts_reader import (
    PostgresAccessGroupCreationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_creation_result_reader import (
    PostgresAccessGroupCreationResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_creation_writer import (
    PostgresAccessGroupCreationWriter,
)
from inframeld_backend.bootstrap.access_group_composition import (
    open_access_group_creation,
    open_access_group_deletion,
    open_access_group_read,
    open_access_group_relationship_change,
)
from inframeld_backend.bootstrap.deletion_status_composition import open_deletion_status_lookup
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.routes.deletion_status_routes import (
    create_deletion_status_router,
)
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.application_account_scenarios import MockApplicationAccountAuthenticator


def group_creation_service(session: AsyncSession) -> AccessGroupCreationService:
    return AccessGroupCreationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        creation_facts_reader=PostgresAccessGroupCreationFactsReader(session),
        creation_writer=PostgresAccessGroupCreationWriter(session),
        creation_result_reader=PostgresAccessGroupCreationResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        creation_fingerprint_service=AccessGroupCreationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )


def group_command(
    project_id: ProjectId, revision: int = 1, name: str = "support-knowledge"
) -> CreateAccessGroupCommand:
    return CreateAccessGroupCommand(
        project_id, revision, ResourceName(name), SubmittedDisplayName("SupportKnowledge")
    )


def group_context(
    project_id: ProjectId, key: str = "create-support-group"
) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.POST, f"/v1/projects/{project_id.value}/access-groups", IdempotencyKey(key)
    )


async def create_group(
    database: Database,
    access: AccessContextDTO,
    project_id: ProjectId,
    revision: int = 1,
    name: str = "support-knowledge",
    key: str = "create-support-group",
) -> AccessGroupCreationResultDTO:
    async with database.session() as session:
        return await group_creation_service(session).create(
            access=access,
            command=group_command(project_id, revision, name),
            context=group_context(project_id, key),
        )


async def change_group(
    database: Database,
    access: AccessContextDTO,
    group: CreatedAccessGroupDTO,
    principal_id: PrincipalId,
    kind: AccessGroupChangeKind,
    revision: int,
    key: str,
) -> AccessGroupRelationshipResultDTO:
    async with open_access_group_relationship_change(database, group_fingerprints()) as service:
        return await service.change(
            access=access,
            command=ChangeAccessGroupRelationshipCommand(
                group.project_id, group.group_id, principal_id, revision, kind
            ),
            context=IdempotencyContextDTO(
                kind.http_method,
                f"/v1/projects/{group.project_id.value}/access-groups/{group.group_id.value}/{kind.collection}/{principal_id.value}",
                IdempotencyKey(key),
            ),
        )


async def delete_group(
    database: Database,
    access: AccessContextDTO,
    group: CreatedAccessGroupDTO,
    revision: int,
    key: str = "delete-support-group",
) -> AccessGroupDeletionResultDTO:
    async with open_access_group_deletion(
        database, group_fingerprints(), DeletionStatusRetentionProfile(30)
    ) as service:
        return await service.delete(
            access=access,
            command=DeleteAccessGroupCommand(group.project_id, group.group_id, revision),
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/projects/{group.project_id.value}/access-groups/{group.group_id.value}",
                IdempotencyKey(key),
            ),
            request_id=RequestId(uuid4()),
        )


def group_fingerprints() -> RequestFingerprintService:
    return RequestFingerprintService(RequestFingerprintKey(b"K" * 32))


def group_http_application(
    database: Database, access: AccessContextDTO, bearer_access: AccessContextDTO
) -> FastAPI:
    authenticator = MockApplicationAccountAuthenticator(access, bearer_access)
    authenticate = HumanSessionDependency(
        authenticator,
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
        access_token_authenticator=authenticator,
    )
    app = FastAPI()
    register_error_handlers(app)
    register_human_oauth_credential_error_handler(app)
    configure_problem_openapi(app)
    app.include_router(
        create_access_group_router(
            authenticate,
            partial(open_access_group_creation, database, group_fingerprints()),
            partial(open_access_group_read, database),
            partial(open_access_group_relationship_change, database, group_fingerprints()),
            partial(
                open_access_group_deletion,
                database,
                group_fingerprints(),
                DeletionStatusRetentionProfile(30),
            ),
        )
    )
    app.include_router(
        create_original_operation_lookup_router(
            authenticate, partial(open_original_operation_lookup, database)
        )
    )
    app.include_router(
        create_deletion_status_router(authenticate, partial(open_deletion_status_lookup, database))
    )
    app.add_middleware(RequestContextMiddleware)
    return app
