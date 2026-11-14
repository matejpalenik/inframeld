from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_item_dto import (
    ModelConnectionGrantItemDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.protocols.model_connection_grant_read_repository import (
    ModelConnectionGrantReadRepository,
)
from inframeld_backend.access.application.protocols.model_connection_grant_repository import (
    ModelConnectionGrantRepository,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
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
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_grant_result_row import (
    ModelConnectionGrantResultRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_model_connection_action_grant_writer import (
    PostgresModelConnectionActionGrantWriter,
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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresModelConnectionGrantRepository(
    ModelConnectionGrantRepository, ModelConnectionGrantReadRepository
):
    """Resolve the target's actual Project before taking its ordered Access turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._writer = PostgresModelConnectionActionGrantWriter(session)

    @override
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeModelConnectionGrantCommand
    ) -> ModelConnectionGrantFactsDTO | None:
        return await self.observe(
            access,
            command.model_connection_id,
            command.action,
            command.recipient_id,
            exclusive=True,
        )

    @override
    async def lock_for_read(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
    ) -> ModelConnectionGrantFactsDTO | None:
        return await self.observe(access, connection_id, action, None, exclusive=False)

    @override
    async def list_assignments(
        self,
        facts: ModelConnectionGrantFactsDTO,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[ModelConnectionGrantItemDTO, ...]:
        grant = ModelConnectionActionGrantRow
        query = select(grant.recipient_principal_id, grant.can_grant).where(
            grant.project_id == facts.project_id.value,
            grant.model_connection_id == facts.model_connection_id.value,
            grant.action == facts.action.value,
        )
        if after is not None:
            query = query.where(grant.recipient_principal_id > after.value)
        try:
            rows = (
                (
                    await self._session.execute(
                        query.order_by(grant.recipient_principal_id).limit(limit)
                    )
                )
                .tuples()
                .all()
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return tuple(
            ModelConnectionGrantItemDTO(PrincipalId(recipient), can_grant)
            for recipient, can_grant in rows
        )

    async def observe(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
        recipient_id: PrincipalId | None,
        *,
        exclusive: bool,
    ) -> ModelConnectionGrantFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Model connection grant facts require an active caller transaction.")
        try:
            scope = await self._lock_scope(
                connection_id, access.actor_principal_id, exclusive=exclusive
            )
            if scope is None:
                return None
            return await self.read_checked_scope(
                access,
                scope,
                action,
                recipient_id,
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _lock_scope(
        self, connection_id: ModelConnectionId, actor: PrincipalId, *, exclusive: bool
    ) -> tuple[OrganizationId, ModelConnectionGrantTargetDTO] | None:
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Model connection grant facts require READ COMMITTED isolation.")
        # This is a reject-only filter. Current authority is read again after both locks.
        membership = (
            select(ProjectMembershipRow.project_id)
            .select_from(ProjectMembershipRow)
            .join(PrincipalRow, PrincipalRow.id == ProjectMembershipRow.principal_id)
            .where(
                PrincipalRow.id == actor.value,
                PrincipalRow.organization_id == ModelConnectionRow.organization_id,
                ProjectMembershipRow.organization_id == ModelConnectionRow.organization_id,
                ProjectMembershipRow.project_id == ModelConnectionRow.project_id,
            )
            .correlate(ModelConnectionRow)
            .exists()
        )
        scope = (
            (
                await self._session.execute(
                    select(ModelConnectionRow.organization_id, ModelConnectionRow.project_id).where(
                        ModelConnectionRow.id == connection_id.value,
                        membership,
                    )
                )
            )
            .tuples()
            .one_or_none()
        )
        if scope is None:
            return None
        organization, project = scope
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
                .where(ProjectRow.id == project, ProjectRow.organization_id == organization)
                .with_for_update(read=not exclusive)
            )
            is None
        ):
            return None
        return OrganizationId(organization), ModelConnectionGrantTargetDTO(
            ProjectId(project), connection_id
        )

    async def read_checked_scope(
        self,
        access: AccessContextDTO,
        scope: tuple[OrganizationId, ModelConnectionGrantTargetDTO],
        action: ModelConnectionAction,
        recipient_id: PrincipalId | None,
    ) -> ModelConnectionGrantFactsDTO | None:
        """Read current actor and target under the caller's already-locked Project turn."""
        organization, target = scope
        project, connection = target.project_id.value, target.model_connection_id.value
        grant = ModelConnectionActionGrantRow
        exact = (
            grant.project_id == project,
            grant.model_connection_id == connection,
            grant.action == action.value,
        )
        delegated = (
            exists()
            .where(
                *exact,
                grant.recipient_principal_id == PrincipalRow.id,
                grant.recipient_kind == PrincipalRow.kind,
                grant.can_grant.is_(True),
            )
            .correlate(PrincipalRow)
        )
        header = (
            ProjectActorQueries.header(access, target.project_id)
            .where(
                PrincipalRow.organization_id == organization.value,
                exists().where(
                    ModelConnectionRow.id == connection,
                    ModelConnectionRow.project_id == project,
                    ModelConnectionRow.organization_id == organization.value,
                    ModelConnectionRow.retired_at.is_(None),
                ),
            )
            .add_columns(delegated)
        )
        row = (await self._session.execute(header)).tuples().one_or_none()
        if row is None:
            return None
        actor, project_row, installation, member, recovering, linked, version, can_grant = row
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        installed = InstallationId(installation)
        candidate = self._candidate_query(organization, target.project_id, installed)
        recipient = (
            (
                await self._session.execute(
                    candidate.add_columns(
                        exists()
                        .where(
                            ApplicationAccountRow.principal_id == PrincipalRow.id,
                            ApplicationAccountRow.organization_id == organization.value,
                            ApplicationAccountRow.project_id == project,
                            ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                            ProjectMembershipRow.project_id == project,
                            ProjectMembershipRow.principal_id == PrincipalRow.id,
                            ProjectMembershipRow.application_principal_id == PrincipalRow.id,
                            ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                        )
                        .correlate(PrincipalRow),
                    ).where(PrincipalRow.id == recipient_id.value)
                )
            )
            .tuples()
            .one_or_none()
            if recipient_id is not None
            else None
        )
        assignment = (
            await self._session.scalar(
                select(grant.can_grant).where(
                    *exact,
                    grant.recipient_principal_id == recipient_id.value,
                    grant.recipient_kind == recipient[0].kind,
                )
            )
            if recipient is not None and recipient_id is not None
            else None
        )
        grantors = (
            (
                await self._session.execute(
                    candidate.where(
                        PrincipalRow.kind == PrincipalKind.HUMAN,
                        delegated,
                    )
                )
            )
            .tuples()
            .all()
            if assignment is True
            else ()
        )
        return ModelConnectionGrantFactsDTO(
            installed,
            organization,
            target.project_id,
            target.model_connection_id,
            action,
            project_row.access_revision,
            PostgresProjectActorMapper.action(
                access=access,
                principal=actor,
                project=project_row,
                member=member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=can_grant,
            ),
            can_grant,
            self._principal(recipient[0]) if recipient is not None else None,
            recipient[2] if recipient is not None else False,
            recipient[1] if recipient is not None else False,
            recipient[3] if recipient is not None else False,
            recipient[4] if recipient is not None else False,
            ActionGrantState(assignment),
            tuple(
                ProjectDepartureCandidatePolicyInput(
                    self._principal(holder),
                    blocked,
                    is_member,
                    coherent,
                    True,
                    False,
                    False,
                )
                for holder, blocked, is_member, coherent in grantors
            ),
        )

    @staticmethod
    def _candidate_query(
        organization: OrganizationId, project: ProjectId, installed: InstallationId
    ) -> Select[tuple[PrincipalRow, bool, bool, bool]]:
        return (
            select(
                PrincipalRow,
                ProjectPrincipalQueries.pending(PrincipalRow.id, installed),
                ProjectPrincipalQueries.membership(PrincipalRow.id, project, organization),
                ProjectPrincipalQueries.coherent_identity(PrincipalRow.id, organization, installed),
            )
            .where(PrincipalRow.organization_id == organization.value)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            PrincipalId(row.id), OrganizationId(row.organization_id), row.kind, row.status
        )

    @override
    async def original(
        self, facts: ModelConnectionGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ModelConnectionGrantResultDTO:
        try:
            row = await self._session.scalar(
                select(ModelConnectionGrantResultRow).where(
                    ModelConnectionGrantResultRow.operation_id == operation.operation_id.value,
                    ModelConnectionGrantResultRow.organization_id == facts.organization_id.value,
                    ModelConnectionGrantResultRow.project_id == facts.project_id.value,
                    ModelConnectionGrantResultRow.model_connection_id
                    == facts.model_connection_id.value,
                    ModelConnectionGrantResultRow.actor_principal_id
                    == facts.actor.principal.id.value,
                    ModelConnectionGrantResultRow.action == facts.action.value,
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None or row.status_code not in (200, 201):
            raise ConflictError("The original model connection grant is unavailable.")
        return ModelConnectionGrantResultDTO(
            ModelConnectionGrantTargetDTO(facts.project_id, facts.model_connection_id),
            PrincipalId(row.recipient_principal_id),
            facts.action,
            row.can_grant,
            row.access_revision,
            row.before_can_grant is not row.can_grant,
            200 if row.status_code == 200 else 201,
            operation,
        )

    @override
    async def save_change(
        self,
        facts: ModelConnectionGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        try:
            await self._writer.save_change(facts, recipient_id, after, operation_id)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def save_result(
        self, facts: ModelConnectionGrantFactsDTO, result: ModelConnectionGrantResultDTO
    ) -> None:
        try:
            await self._writer.save_result(facts, result)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
