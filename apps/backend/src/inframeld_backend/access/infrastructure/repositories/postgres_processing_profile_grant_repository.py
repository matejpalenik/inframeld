from typing import override

from sqlalchemy import exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_facts_dto import (
    ProcessingProfileGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_item_dto import (
    ProcessingProfileGrantItemDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_target_dto import (
    ProcessingProfileGrantTargetDTO,
)
from inframeld_backend.access.application.protocols.processing_profile_grant_repository import (
    ProcessingProfileGrantRepository,
)
from inframeld_backend.access.domain.entities.principal import Principal
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
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.processing_profile_grant_result_row import (
    ProcessingProfileGrantResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.writers.postgres_processing_profile_action_grant_writer import (
    PostgresProcessingProfileActionGrantWriter,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.readers.processing_profile_project_lock import (
    ProcessingProfileProjectLock,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresProcessingProfileGrantRepository(ProcessingProfileGrantRepository):
    """Resolve the target's actual Project before taking its ordered Access turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._writer = PostgresProcessingProfileActionGrantWriter(session)

    @override
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeProcessingProfileGrantCommand
    ) -> ProcessingProfileGrantFactsDTO | None:
        return await self.observe(
            access,
            command.processing_profile_id,
            command.action,
            command.recipient_id,
            exclusive=True,
        )

    @override
    async def lock_for_read(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
    ) -> ProcessingProfileGrantFactsDTO | None:
        return await self.observe(access, profile_id, action, None, exclusive=False)

    @override
    async def list_assignments(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[ProcessingProfileGrantItemDTO, ...]:
        grant = ProcessingProfileActionGrantRow
        query = select(grant.recipient_principal_id, grant.can_grant).where(
            grant.project_id == facts.project_id.value,
            grant.processing_profile_id == facts.processing_profile_id.value,
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
            ProcessingProfileGrantItemDTO(PrincipalId(recipient), can_grant)
            for recipient, can_grant in rows
        )

    async def observe(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
        recipient_id: PrincipalId | None,
        *,
        exclusive: bool,
    ) -> ProcessingProfileGrantFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError(
                "Processing Profile grant facts require an active caller transaction."
            )
        try:
            scope = await self._lock_scope(
                profile_id, access.actor_principal_id, exclusive=exclusive
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
        self, profile_id: ProcessingProfileId, actor: PrincipalId, *, exclusive: bool
    ) -> tuple[OrganizationId, ProcessingProfileGrantTargetDTO] | None:
        # This is a reject-only filter. Current authority is read again after both locks.
        membership = (
            select(ProjectMembershipRow.project_id)
            .select_from(ProjectMembershipRow)
            .join(PrincipalRow, PrincipalRow.id == ProjectMembershipRow.principal_id)
            .where(
                PrincipalRow.id == actor.value,
                PrincipalRow.organization_id == ProcessingProfileRow.organization_id,
                ProjectMembershipRow.organization_id == ProcessingProfileRow.organization_id,
                ProjectMembershipRow.project_id == ProcessingProfileRow.project_id,
            )
            .correlate(ProcessingProfileRow)
            .exists()
        )
        scope = (
            (
                await self._session.execute(
                    select(
                        ProcessingProfileRow.organization_id, ProcessingProfileRow.project_id
                    ).where(
                        ProcessingProfileRow.id == profile_id.value,
                        membership,
                    )
                )
            )
            .tuples()
            .one_or_none()
        )
        if scope is None:
            return None
        organization, project = OrganizationId(scope[0]), ProjectId(scope[1])
        locked = await ProcessingProfileProjectLock.acquire(
            self._session, actor, project, shared=not exclusive
        )
        if locked is None:
            return None
        if locked != organization.value:
            raise RuntimeError("Profile grant lock changed the target's Organization.")
        return organization, ProcessingProfileGrantTargetDTO(project, profile_id)

    async def read_checked_scope(
        self,
        access: AccessContextDTO,
        scope: tuple[OrganizationId, ProcessingProfileGrantTargetDTO],
        action: ProcessingProfileAction,
        recipient_id: PrincipalId | None,
    ) -> ProcessingProfileGrantFactsDTO | None:
        """Read current actor and target under the caller's already-locked Project turn."""
        organization, target = scope
        project, profile = target.project_id.value, target.processing_profile_id.value
        grant = ProcessingProfileActionGrantRow
        exact = (
            grant.project_id == project,
            grant.processing_profile_id == profile,
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
                    ProcessingProfileRow.id == profile,
                    ProcessingProfileRow.project_id == project,
                    ProcessingProfileRow.organization_id == organization.value,
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
        return ProcessingProfileGrantFactsDTO(
            installed,
            organization,
            target.project_id,
            target.processing_profile_id,
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
        self, facts: ProcessingProfileGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ProcessingProfileGrantResultDTO:
        try:
            row = await self._session.scalar(
                select(ProcessingProfileGrantResultRow).where(
                    ProcessingProfileGrantResultRow.operation_id == operation.operation_id.value,
                    ProcessingProfileGrantResultRow.organization_id == facts.organization_id.value,
                    ProcessingProfileGrantResultRow.project_id == facts.project_id.value,
                    ProcessingProfileGrantResultRow.processing_profile_id
                    == facts.processing_profile_id.value,
                    ProcessingProfileGrantResultRow.actor_principal_id
                    == facts.actor.principal.id.value,
                    ProcessingProfileGrantResultRow.action == facts.action.value,
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None or row.status_code not in (200, 201):
            raise ConflictError("The original Processing Profile grant is unavailable.")
        return ProcessingProfileGrantResultDTO(
            ProcessingProfileGrantTargetDTO(facts.project_id, facts.processing_profile_id),
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
        facts: ProcessingProfileGrantFactsDTO,
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
        self, facts: ProcessingProfileGrantFactsDTO, result: ProcessingProfileGrantResultDTO
    ) -> None:
        try:
            await self._writer.save_result(facts, result)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
