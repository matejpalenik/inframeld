from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_deletion_facts_dto import (
    ProjectDeletionFactsDTO,
)
from inframeld_backend.access.application.protocols.project_deletion_facts_reader import (
    ProjectDeletionFactsReader,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresProjectDeletionFactsReader(ProjectDeletionFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectDeletionFactsDTO | None:
        """Observe current exact Delete-project facts in the caller's READ COMMITTED transaction.

        Take Organization-shared then Project-exclusive coordination and refresh
        credential, actor, membership, action and revision facts after waits.
        Include a blocked Project for ordinary original recovery, never invent
        active status or saved authority. Missing scope returns None.
        Commit, rollback and the original five-second deadline stay with caller.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Project deletion requires the active caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Project deletion requires READ COMMITTED isolation.")
        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None:
            return None
        if (
            await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == organization)
                .with_for_update(read=True)
            )
            is None
        ):
            return None
        if (
            await self._session.scalar(
                select(ProjectRow.id)
                .where(
                    ProjectRow.id == project_id.value, ProjectRow.organization_id == organization
                )
                .with_for_update()
            )
            is None
        ):
            return None
        granted = (
            exists()
            .where(
                ProjectActionGrantRow.project_id == ProjectRow.id,
                ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                ProjectActionGrantRow.action == "delete-project",
            )
            .correlate(ProjectRow, PrincipalRow)
        )
        row = (
            (
                await self._session.execute(
                    ProjectActorQueries.header(access, project_id).add_columns(granted)
                )
            )
            .tuples()
            .one_or_none()
        )
        if row is None:
            return None
        principal, project, installation, member, recovering, linked, version, has_action = row
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return ProjectDeletionFactsDTO(
            InstallationId(installation),
            OrganizationId(project.organization_id),
            project_id,
            project.access_revision,
            PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=has_action,
            ),
        )
