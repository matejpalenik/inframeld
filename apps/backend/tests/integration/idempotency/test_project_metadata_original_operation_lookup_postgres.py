"""Find the original metadata operation only under its current exact authority."""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_metadata_scenarios import (
    metadata_service,
    seed_another_metadata_project,
    seed_metadata_project,
)

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_original_request_lookup_preserves_exact_project_installation_and_current_metadata_grant(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
        other = await seed_another_metadata_project(session, seed)
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    context = OperationAdmissionContextDTO(
        "PATCH", "/v1/projects/{project_id}/metadata", IdempotencyKey("original")
    )
    async with database.session() as session:
        admitted = await metadata_service(session).update(
            access=access,
            command=UpdateProjectMetadataCommand(seed.project_id, 0, ResourceName("support")),
            context=context,
        )
    installed = await PostgresInstallationIdentityReader(database).read()
    query = LookupOriginalOperationQuery(
        installed,
        seed.organization_id,
        seed.project_id,
        "PATCH",
        context.requested_route,
        context.key,
        OperationLookupAuthority(OperationLookupAuthorityFamily.PROJECT_ACTION_USE, seed.action),
    )
    async with open_original_operation_lookup(database) as service:
        original = await service.lookup(access=access, query=query)
    assert (
        isinstance(original, CompletedSynchronousOperationDTO)
        and original.operation_id == admitted.operation.operation_id
    )
    async with open_original_operation_lookup(database) as service:
        assert isinstance(
            await service.lookup(access=access, query=replace(query, project_id=other.project_id)),
            UnresolvedOperationDTO,
        )
    async with open_original_operation_lookup(database) as service:
        with pytest.raises(ResourceNotFoundError):
            await service.lookup(
                access=access, query=replace(query, installation_id=InstallationId(uuid4()))
            )
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == seed.project_id.value
            )
        )
    for key in (context.key, IdempotencyKey("unknown")):
        async with open_original_operation_lookup(database) as service:
            with pytest.raises(AccessDeniedError):
                await service.lookup(access=access, query=replace(query, key=key))
