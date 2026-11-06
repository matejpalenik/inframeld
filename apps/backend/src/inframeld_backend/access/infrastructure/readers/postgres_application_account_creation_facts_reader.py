from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_facts_dto import (
    ApplicationAccountCreationFactsDTO,
)
from inframeld_backend.access.application.protocols.application_account_creation_facts_reader import (
    ApplicationAccountCreationFactsReader,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
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


class PostgresApplicationAccountCreationFactsReader(ApplicationAccountCreationFactsReader):
    """Take the existing Access turn, then observe fresh creation authority."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ApplicationAccountCreationFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Account creation requires the active caller transaction.")
        try:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Account creation requires READ COMMITTED isolation.")
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
                        ProjectRow.id == project_id.value,
                        ProjectRow.organization_id == organization,
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
                    ProjectActionGrantRow.action == ProjectAction.CREATE_APPLICATION_ACCOUNTS.value,
                )
                .correlate(PrincipalRow, ProjectRow)
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
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            return None
        principal, project, installed, member, recovering, linked, version, has_grant = row
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return ApplicationAccountCreationFactsDTO(
            OrganizationId(principal.organization_id),
            ProjectId(project.id),
            project.access_revision,
            PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=has_grant,
            ),
        )
