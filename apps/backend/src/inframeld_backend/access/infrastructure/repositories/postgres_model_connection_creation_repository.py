from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_facts_dto import (
    ModelConnectionCreationFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.protocols.model_connection_creation_repository import (
    ModelConnectionCreationRepository,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.model_connection_creation_result_row import (
    ModelConnectionCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_model_connection_creation_writer import (
    PostgresModelConnectionCreationWriter,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class PostgresModelConnectionCreationRepository(ModelConnectionCreationRepository):
    """Keep creation and original replay behind the current Project Access turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._writer = PostgresModelConnectionCreationWriter(session)

    @override
    async def lock_for_creation(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> ModelConnectionCreationFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Model connection creation requires an active caller transaction.")
        try:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Model connection creation requires READ COMMITTED isolation.")
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
                    ProjectActionGrantRow.action == ProjectAction.CREATE_MODEL_CONNECTIONS.value,
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
        principal, project, installation, member, recovering, linked, version, has_grant = row
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return ModelConnectionCreationFactsDTO(
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

    @override
    async def original(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCreationDTO:
        try:
            row = await self._session.scalar(
                select(ModelConnectionCreationResultRow).where(
                    ModelConnectionCreationResultRow.operation_id == operation.operation_id.value,
                    ModelConnectionCreationResultRow.organization_id == facts.organization_id.value,
                    ModelConnectionCreationResultRow.project_id == facts.project_id.value,
                    ModelConnectionCreationResultRow.creator_principal_id
                    == access.actor_principal_id.value,
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None or row.initial_actions != [action.value for action in ModelConnectionAction]:
            raise ConflictError("The original model connection creation result is unavailable.")
        return ModelConnectionCreationDTO(
            ModelConnectionDTO(
                ProjectId(row.project_id),
                ModelConnectionId(row.model_connection_id),
                ResourceName(row.name),
                row.display_name,
                ModelConnectionAccessDTO(
                    ModelConnectionProvider(row.provider),
                    row.base_url,
                    row.api_version,
                    ModelConnectionAuthentication(row.authentication),
                ),
                connection_access_revision=0,
                credential_present=False,
                credential_revision=0,
            ),
            operation,
            row.project_access_revision,
            tuple(ModelConnectionAction),
        )

    @override
    async def save(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation_id: OperationId,
        connection: ModelConnectionDTO,
        initial_actions: tuple[ModelConnectionAction, ...],
    ) -> None:
        try:
            await self._writer.create(
                actor=access.actor_principal_id,
                facts=facts,
                operation_id=operation_id,
                connection=connection,
                initial_actions=initial_actions,
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
