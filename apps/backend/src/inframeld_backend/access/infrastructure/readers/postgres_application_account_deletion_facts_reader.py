from typing import override

from sqlalchemy import DateTime, String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_facts_dto import (
    ApplicationAccountDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.protocols.application_account_deletion_facts_reader import (
    ApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_deletion_result_row import (
    ApplicationAccountDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresApplicationAccountDeletionFactsReader(ApplicationAccountDeletionFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, command: DeleteApplicationAccountCommand
    ) -> ApplicationAccountDeletionFactsDTO | None:
        try:
            with self._session.no_autoflush:
                await self._require_caller_transaction()
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
                            ProjectRow.id == command.project_id.value,
                            ProjectRow.organization_id == organization,
                        )
                        .with_for_update()
                    )
                    is None
                ):
                    return None

                account = await self._session.scalar(
                    select(ApplicationAccountRow)
                    .where(
                        ApplicationAccountRow.principal_id
                        == command.application_principal_id.value,
                        ApplicationAccountRow.organization_id == organization,
                        ApplicationAccountRow.project_id == command.project_id.value,
                        ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if account is None:
                    return None
                application = await self._session.scalar(
                    select(PrincipalRow)
                    .where(
                        PrincipalRow.id == account.principal_id,
                        PrincipalRow.organization_id == organization,
                        PrincipalRow.kind == PrincipalKind.APPLICATION,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if application is None:
                    raise RuntimeError("Retirement facts changed the account principal binding.")
                key = ApplicationKeyRow
                keys = (
                    (
                        await self._session.execute(
                            select(
                                key.installation_id,
                                key.organization_id,
                                key.project_id,
                                key.created_at,
                                key.revoked_at,
                            )
                            .where(key.application_principal_id == account.principal_id)
                            .order_by(key.key_id)
                            .with_for_update()
                        )
                    )
                    .tuples()
                    .all()
                )

                grant = ApplicationActionGrantRow
                granted = (
                    exists()
                    .where(
                        grant.project_id == ProjectRow.id,
                        grant.application_principal_id == account.principal_id,
                        grant.recipient_principal_id == PrincipalRow.id,
                        grant.recipient_kind == PrincipalKind.HUMAN,
                        grant.action == ApplicationAccountAction.DELETE_ACCOUNT.value,
                    )
                    .correlate(PrincipalRow, ProjectRow)
                )
                observed = (
                    (
                        await self._session.execute(
                            ProjectActorQueries.header(access, command.project_id).add_columns(
                                granted
                            )
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                if observed is None:
                    return None
                principal, project, installed, member, recovering, linked, version, can_delete = (
                    observed
                )
                now = await self._session.scalar(
                    select(func.clock_timestamp(type_=DateTime(timezone=True)))
                )
                if installed is None or now is None:
                    raise DependencyUnavailableError()
                if any(
                    installation_id != installed
                    or organization_id != organization
                    or project_id != account.project_id
                    or (revoked_at is None and created_at > now)
                    for installation_id, organization_id, project_id, created_at, revoked_at in keys
                ):
                    raise RuntimeError("Retirement facts changed an associated key binding.")

                return ApplicationAccountDeletionFactsDTO(
                    organization_id=OrganizationId(account.organization_id),
                    project_id=ProjectId(account.project_id),
                    installation_id=InstallationId(installed),
                    actor=PostgresProjectActorMapper.action(
                        access=access,
                        principal=principal,
                        project=project,
                        member=member,
                        recovering=recovering,
                        linked=linked,
                        version=version,
                        granted=can_delete,
                    ),
                    application_principal=Principal(
                        PrincipalId(application.id),
                        OrganizationId(application.organization_id),
                        application.kind,
                        application.status,
                    ),
                    access_revision=project.access_revision,
                    checked_at=now,
                )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationAccountDeletionRecordDTO | None:
        try:
            with self._session.no_autoflush:
                await self._require_caller_transaction()
                original, parent = ApplicationAccountDeletionResultRow, IdempotencyReservationRow
                result = (
                    (
                        await self._session.execute(
                            select(original, parent.requested_route)
                            .join(parent, parent.operation_id == original.operation_id)
                            .where(
                                original.operation_id == operation_id.value,
                                original.organization_id == organization_id.value,
                                original.project_id == project_id.value,
                                original.actor_principal_id == actor_principal_id.value,
                                parent.organization_id == original.organization_id,
                                parent.project_id == original.project_id,
                                parent.principal_id == original.actor_principal_id,
                                parent.method == HttpMethod.DELETE.value,
                                parent.lookup_authority_family.is_(None),
                                parent.lookup_action_id.is_(None),
                                parent.state == OperationReservationState.REPLAYABLE,
                                parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                                parent.expires_at > func.clock_timestamp(),
                            )
                            .execution_options(populate_existing=True)
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if result is None:
            return None
        row, saved_route = result
        route = f"/v1/projects/{row.project_id}/application-accounts/{row.application_principal_id}"
        try:
            RevisionValidation.require(row.before_revision)
            RevisionValidation.require(row.access_revision)
            if saved_route != route or row.access_revision != row.before_revision + 1:
                raise ValueError("Incoherent retirement original.")
            return ApplicationAccountDeletionRecordDTO(
                operation_id=OperationId(row.operation_id),
                installation_id=InstallationId(row.installation_id),
                organization_id=OrganizationId(row.organization_id),
                project_id=ProjectId(row.project_id),
                actor_principal_id=PrincipalId(row.actor_principal_id),
                application_principal_id=PrincipalId(row.application_principal_id),
                access_revision=row.access_revision,
            )
        except (ValueError, TypeError):
            raise ConflictError("The original application-account result is incoherent.") from None

    async def _require_caller_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Application retirement requires the active caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Application retirement requires READ COMMITTED isolation.")
