import asyncio
from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_audience_dto import (
    ProjectUploadAudienceDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_facts_dto import (
    ProjectUploadDefaultFactsDTO,
)
from inframeld_backend.access.application.dtos.upload_default_group_facts_dto import (
    UploadDefaultGroupFactsDTO,
)
from inframeld_backend.access.application.protocols.project_upload_audience_reader import (
    ProjectUploadAudienceReader,
)
from inframeld_backend.access.application.protocols.project_upload_default_facts_reader import (
    ProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)


class PostgresProjectUploadDefaultFactsReader(
    ProjectUploadDefaultFactsReader, ProjectUploadAudienceReader
):
    """Refresh one saved set and its complete management facts after ordered caller locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectUploadDefaultFactsDTO | None:
        return await self._observe(
            access=access, project_id=project_id, proposed=None, exclusive=False
        )

    @override
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: SetProjectUploadDefaultCommand
    ) -> ProjectUploadDefaultFactsDTO | None:
        return await self._observe(
            access=access, project_id=command.project_id, proposed=command.audience, exclusive=True
        )

    async def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Upload-default facts require the active caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Upload-default facts require READ COMMITTED isolation.")

    async def _lock_project(
        self, organization_id: OrganizationId, project_id: ProjectId, *, exclusive: bool
    ) -> bool:
        organization = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization_id.value)
            .with_for_update(read=True)
        )
        if organization is None:
            return False
        return (
            await self._session.scalar(
                select(ProjectRow.id)
                .where(
                    ProjectRow.organization_id == organization_id.value,
                    ProjectRow.id == project_id.value,
                )
                .with_for_update(read=not exclusive)
            )
            is not None
        )

    @override
    async def read_upload_audience(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectUploadAudienceDTO:
        try:
            async with asyncio.timeout(5):
                await self._require_transaction()
                if not await self._lock_project(organization_id, project_id, exclusive=False):
                    raise ResourceNotFoundError()
                revision = await self._session.scalar(
                    select(ProjectRow.access_revision)
                    .where(
                        ProjectRow.id == project_id.value,
                        ProjectRow.organization_id == organization_id.value,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
                if revision is None:
                    raise ResourceNotFoundError()
                return ProjectUploadAudienceDTO(
                    organization_id,
                    project_id,
                    revision,
                    await self._saved_audience(organization_id, project_id),
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _saved_audience(
        self, organization_id: OrganizationId, project_id: ProjectId
    ) -> UploadAudience | None:
        links = tuple(
            await self._session.scalars(
                select(ProjectUploadDefaultGroupRow)
                .where(ProjectUploadDefaultGroupRow.project_id == project_id.value)
                .order_by(ProjectUploadDefaultGroupRow.group_id)
                .execution_options(populate_existing=True, autoflush=False)
            )
        )
        if not links:
            return None
        if any(link.organization_id != organization_id.value for link in links):
            raise DependencyUnavailableError("The stored default has incoherent Project scope.")
        identifiers = tuple(link.group_id for link in links)
        existing = set(
            await self._session.scalars(
                select(AccessGroupRow.id).where(
                    AccessGroupRow.project_id == project_id.value,
                    AccessGroupRow.id.in_(identifiers),
                )
            )
        )
        if existing != set(identifiers):
            raise DependencyUnavailableError("The complete saved upload audience is unavailable.")
        return UploadAudience(tuple(AccessGroupId(identifier) for identifier in identifiers))

    async def _observe(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        proposed: UploadAudience | None,
        exclusive: bool,
    ) -> ProjectUploadDefaultFactsDTO | None:
        try:
            async with asyncio.timeout(5):
                await self._require_transaction()
                organization = await self._session.scalar(
                    select(PrincipalRow.organization_id).where(
                        PrincipalRow.id == access.actor_principal_id.value
                    )
                )
                if organization is None:
                    return None
                organization_id = OrganizationId(organization)
                if not await self._lock_project(organization_id, project_id, exclusive=exclusive):
                    return None
                granted = (
                    exists()
                    .where(
                        ProjectActionGrantRow.project_id == ProjectRow.id,
                        ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                        ProjectActionGrantRow.action == ProjectAction.MANAGE_UPLOAD_DEFAULTS.value,
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
                (
                    principal,
                    project,
                    installation,
                    member,
                    recovering,
                    linked,
                    version,
                    has_action,
                ) = row
                if installation is None:
                    raise DependencyUnavailableError("The installation identity is unavailable.")
                audience = await self._saved_audience(organization_id, project_id)
                needed: set[AccessGroupId] = (
                    set(audience.group_ids) if audience is not None else set()
                )
                if proposed is not None:
                    needed.update(proposed.group_ids)
                observations: list[UploadDefaultGroupFactsDTO] = []
                if needed:
                    group_member = (
                        exists()
                        .where(
                            GroupMembershipRow.project_id == AccessGroupRow.project_id,
                            GroupMembershipRow.group_id == AccessGroupRow.id,
                            GroupMembershipRow.principal_id == access.actor_principal_id.value,
                        )
                        .correlate(AccessGroupRow)
                    )
                    group_manager = (
                        exists()
                        .where(
                            GroupManagerRow.project_id == AccessGroupRow.project_id,
                            GroupManagerRow.group_id == AccessGroupRow.id,
                            GroupManagerRow.principal_id == access.actor_principal_id.value,
                            GroupManagerRow.principal_kind == principal.kind,
                        )
                        .correlate(AccessGroupRow)
                    )
                    group_action = (
                        exists()
                        .where(
                            GroupActionGrantRow.project_id == AccessGroupRow.project_id,
                            GroupActionGrantRow.group_id == AccessGroupRow.id,
                            GroupActionGrantRow.recipient_principal_id
                            == access.actor_principal_id.value,
                            GroupActionGrantRow.recipient_kind == principal.kind,
                            GroupActionGrantRow.action.in_(
                                tuple(action.value for action in AccessGroupAction)
                            ),
                        )
                        .correlate(AccessGroupRow)
                    )
                    groups = (
                        (
                            await self._session.execute(
                                select(AccessGroupRow.id, group_member, group_manager, group_action)
                                .where(
                                    AccessGroupRow.project_id == project_id.value,
                                    AccessGroupRow.id.in_(tuple(group.value for group in needed)),
                                )
                                .execution_options(populate_existing=True, autoflush=False)
                            )
                        )
                        .tuples()
                        .all()
                    )
                    current = {
                        identifier: (is_member, is_manager, has_action)
                        for identifier, is_member, is_manager, has_action in groups
                    }
                    for group in sorted(needed, key=lambda group: group.value):
                        relationships = current.get(group.value)
                        observations.append(
                            UploadDefaultGroupFactsDTO(
                                group,
                                project_id if relationships is not None else None,
                                relationships[0] if relationships is not None else False,
                                relationships[1] if relationships is not None else False,
                                relationships[2] if relationships is not None else False,
                            )
                        )
                return ProjectUploadDefaultFactsDTO(
                    organization_id,
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
                    audience,
                    tuple(observations),
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
