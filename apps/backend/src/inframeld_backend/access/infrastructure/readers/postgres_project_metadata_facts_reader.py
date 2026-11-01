import asyncio
from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_authorization_facts_dto import (
    ProjectMetadataAuthorizationFactsDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_facts_reader import (
    ProjectMetadataFactsReader,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectMetadataFactsReader(ProjectMetadataFactsReader):
    """Read fresh facts after ordered Access locks, using the caller's short transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Metadata facts require an active caller transaction.")

    @override
    async def scope(self, *, access: AccessContextDTO) -> ResourceNameScopeDTO:
        self._require_transaction()
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError()
        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None:
            raise ResourceNotFoundError()
        return ResourceNameScopeDTO(InstallationId(installed), OrganizationId(organization))

    @override
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        scope = await self.scope(access=access)
        facts = await PostgresProjectActionFactsReader(self._session).read_action_facts(
            access=access,
            action_id=ActionId("edit-project-metadata"),
            target=ProjectActionTargetDTO(project_id),
        )
        if facts is None:
            return None
        if facts.principal.organization_id != scope.organization_id:
            raise RuntimeError("Metadata facts changed their Organization.")
        return ProjectMetadataAuthorizationFactsDTO(project_id, scope.installation_id, facts)

    @override
    async def read_for_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        try:
            async with asyncio.timeout(5):
                scope = await self.scope(access=access)
                organization = await self._session.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == scope.organization_id.value)
                    .with_for_update(read=True)
                )
                if organization is None:
                    return None
                locked = await self._session.scalar(
                    select(ProjectRow.id)
                    .where(
                        ProjectRow.id == project_id.value,
                        ProjectRow.organization_id == organization,
                    )
                    .with_for_update()
                )
                if locked is None:
                    return None
                return await self.read(access=access, project_id=project_id)
        except TimeoutError:
            raise DependencyUnavailableError(
                "Metadata authorization exceeded its database deadline."
            ) from None
