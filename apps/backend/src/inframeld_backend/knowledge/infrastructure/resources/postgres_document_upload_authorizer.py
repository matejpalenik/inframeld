from typing import override

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.protocols.document_upload_authorizer import (
    DocumentUploadAuthorizer,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresDocumentUploadAuthorizer(DocumentUploadAuthorizer):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def require_current(
        self, *, access: AccessContextDTO, command: UploadDocumentCommand
    ) -> ArtifactScopeDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Document upload authority requires the active caller transaction.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Document upload authority requires READ COMMITTED isolation.")

        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None or (
            await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == organization)
                .with_for_update()
            )
            is None
        ):
            raise ResourceNotFoundError()

        # The supported v1 installation has a single Organization. Its turn
        # also serializes Document occupancy across every one of its Projects.
        if tuple(await self._session.scalars(select(OrganizationRow.id).limit(2))) != (
            organization,
        ):
            raise DependencyUnavailableError("The installation Organization cannot be confirmed.")

        project_id = command.project_id
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
            raise ResourceNotFoundError()
        found = (
            (await self._session.execute(ProjectActorQueries.header(access, project_id)))
            .tuples()
            .one_or_none()
        )
        if found is None:
            raise ResourceNotFoundError()
        principal, project, installed, member, recovering, linked, version = found
        if installed is None or principal.organization_id != organization:
            raise DependencyUnavailableError("The current upload scope cannot be confirmed.")
        requested = {group.value for group in command.audience.group_ids}
        granted = set(
            await self._session.scalars(
                select(AccessGroupRow.id)
                .join(
                    GroupActionGrantRow,
                    (GroupActionGrantRow.project_id == AccessGroupRow.project_id)
                    & (GroupActionGrantRow.group_id == AccessGroupRow.id),
                )
                .where(
                    AccessGroupRow.project_id == project.id,
                    AccessGroupRow.id.in_(requested),
                    GroupActionGrantRow.recipient_principal_id == principal.id,
                    GroupActionGrantRow.recipient_kind == principal.kind,
                    GroupActionGrantRow.action == AccessGroupAction.ADD_DOCUMENTS.value,
                )
            )
        )
        facts = PostgresProjectActorMapper.action(
            access=access,
            principal=principal,
            project=project,
            member=member,
            recovering=recovering,
            linked=linked,
            version=version,
            granted=granted == requested,
        )
        PrincipalAccessEvaluationService.require_human(access=access, principal=facts.principal)
        ActionAuthorizationService.require_authorization_from_facts(access=access, facts=facts)
        return ArtifactScopeDTO(InstallationId(installed), OrganizationId(organization), project_id)
