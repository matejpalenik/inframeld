import asyncio
from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.protocols.application_account_grant_management_facts_reader import (
    ApplicationAccountGrantManagementFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresApplicationAccountGrantManagementFactsReader(
    ApplicationAccountGrantManagementFactsReader
):
    """Observe exact current authority after compatible Organization and Project locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ApplicationAccountGrantManagementFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Grant facts require the caller's active transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError("Grant coordination requires READ COMMITTED isolation.")
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

                    exact = (
                        exists()
                        .where(
                            ApplicationActionGrantRow.project_id == ProjectRow.id,
                            ApplicationActionGrantRow.application_principal_id
                            == application_principal_id.value,
                            ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                            ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                            ApplicationActionGrantRow.action == action_id.value,
                            ApplicationActionGrantRow.can_grant.is_(True),
                        )
                        .correlate(PrincipalRow, ProjectRow)
                    )
                    target_principal = aliased(PrincipalRow)
                    query = (
                        ProjectActorQueries.header(access, project_id)
                        .join(
                            ApplicationAccountRow, ApplicationAccountRow.project_id == ProjectRow.id
                        )
                        .join(
                            target_principal,
                            target_principal.id == ApplicationAccountRow.principal_id,
                        )
                        .where(
                            ApplicationAccountRow.principal_id == application_principal_id.value,
                            ApplicationAccountRow.organization_id == ProjectRow.organization_id,
                            ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                            target_principal.kind == PrincipalKind.APPLICATION,
                            target_principal.organization_id == ProjectRow.organization_id,
                            target_principal.status == PrincipalStatus.ACTIVE,
                            exists()
                            .where(
                                ProjectMembershipRow.project_id == ProjectRow.id,
                                ProjectMembershipRow.organization_id == ProjectRow.organization_id,
                                ProjectMembershipRow.principal_id == application_principal_id.value,
                                ProjectMembershipRow.application_principal_id
                                == application_principal_id.value,
                                ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                            )
                            .correlate(ProjectRow),
                        )
                        .add_columns(exact)
                    )
                    header = (await self._session.execute(query)).tuples().one_or_none()
                    if header is None:
                        return None
                    (
                        principal,
                        project,
                        installed,
                        project_member,
                        pending,
                        linked,
                        version,
                        delegated,
                    ) = header
                    if installed is None:
                        raise DependencyUnavailableError()
                    installation = InstallationId(installed)
                    organization_id = OrganizationId(organization)
                    recipient_pending = ProjectPrincipalQueries.pending(
                        PrincipalRow.id, installation
                    )
                    recipient_member = ProjectPrincipalQueries.membership(
                        PrincipalRow.id, project_id, organization_id
                    )
                    recipient_coherent = ProjectPrincipalQueries.coherent_identity(
                        PrincipalRow.id, organization_id, installation
                    )
                    assignment_scope = (
                        ApplicationActionGrantRow.project_id == project_id.value,
                        ApplicationActionGrantRow.application_principal_id
                        == application_principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                        ApplicationActionGrantRow.action == action_id.value,
                    )
                    recipient = (
                        (
                            await self._session.execute(
                                select(
                                    PrincipalRow,
                                    recipient_pending,
                                    recipient_member,
                                    recipient_coherent,
                                )
                                .where(
                                    PrincipalRow.id == recipient_principal_id.value,
                                    PrincipalRow.organization_id == organization,
                                )
                                .execution_options(populate_existing=True, autoflush=False)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    assignment = await self._session.scalar(
                        select(ApplicationActionGrantRow.can_grant).where(
                            ApplicationActionGrantRow.project_id == project_id.value,
                            ApplicationActionGrantRow.application_principal_id
                            == application_principal_id.value,
                            ApplicationActionGrantRow.recipient_principal_id
                            == recipient_principal_id.value,
                            ApplicationActionGrantRow.action == action_id.value,
                        )
                    )
                    candidate_grant = (
                        exists()
                        .where(*assignment_scope, ApplicationActionGrantRow.can_grant.is_(True))
                        .correlate(PrincipalRow)
                    )
                    candidate_rows = (
                        (
                            await self._session.execute(
                                select(
                                    PrincipalRow,
                                    recipient_pending,
                                    recipient_member,
                                    recipient_coherent,
                                )
                                .where(
                                    PrincipalRow.organization_id == organization, candidate_grant
                                )
                                .execution_options(populate_existing=True, autoflush=False)
                            )
                        )
                        .tuples()
                        .all()
                    )
                    candidates = tuple(
                        ProjectDepartureCandidatePolicyInput(
                            principal=self._principal(row),
                            has_pending_recovery=blocked,
                            is_project_member=membership,
                            has_coherent_identity=coherent,
                            can_grant=True,
                            is_group_member=False,
                            is_group_manager=False,
                        )
                        for row, blocked, membership, coherent in candidate_rows
                    )
                    return ApplicationAccountGrantManagementFactsDTO(
                        installation_id=installation,
                        organization_id=organization_id,
                        project_id=project_id,
                        application_principal_id=application_principal_id,
                        action_id=action_id,
                        access_revision=project.access_revision,
                        actor=PostgresProjectActorMapper.action(
                            access=access,
                            principal=principal,
                            project=project,
                            member=project_member,
                            recovering=pending,
                            linked=linked,
                            version=version,
                            granted=delegated,
                        ),
                        actor_can_grant=delegated,
                        recipient=self._principal(recipient[0]) if recipient is not None else None,
                        recipient_has_pending_recovery=recipient[1]
                        if recipient is not None
                        else False,
                        recipient_is_project_member=recipient[2]
                        if recipient is not None
                        else False,
                        recipient_has_coherent_identity=recipient[3]
                        if recipient is not None
                        else False,
                        assignment=ActionGrantState(can_grant=assignment),
                        grantors=candidates,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            id=PrincipalId(row.id),
            organization_id=OrganizationId(row.organization_id),
            kind=row.kind,
            status=row.status,
        )
