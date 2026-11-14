from datetime import datetime
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, String, delete, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.protocols.application_account_deletion_writer import (
    ApplicationAccountDeletionWriter,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_deletion_result_row import (
    ApplicationAccountDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_name_reservation_row import (
    ApplicationAccountNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresApplicationAccountDeletionWriter(ApplicationAccountDeletionWriter):
    """Persist exact-account effects under the coordination already held by the reader."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self,
        *,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Application retirement requires the active caller transaction.")
        RevisionValidation.require(expected_project_revision)
        RevisionValidation.require(original.access_revision)
        if original.access_revision != expected_project_revision + 1:
            raise RuntimeError("Application retirement changed the checked revision transition.")
        try:
            with self._session.no_autoflush:
                isolation = await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                if isolation != "read committed":
                    raise RuntimeError("Application retirement requires READ COMMITTED isolation.")
                await self._require_reservation(original)
                previous = await self._retire_account(
                    original, expected_project_revision, checked_at
                )
                await self._remove_relationships(original)
                self._session.add(
                    AccessAuditEventRow(
                        id=uuid4(),
                        organization_id=original.organization_id.value,
                        project_id=original.project_id.value,
                        actor_kind="human",
                        actor_principal_id=original.actor_principal_id.value,
                        affected_principal_id=original.application_principal_id.value,
                        event_type="application_account_retired",
                        target_kind="application_account",
                        target_id=original.application_principal_id.value,
                        action=ApplicationAccountAction.DELETE_ACCOUNT.value,
                        before_values={
                            "status": previous.value,
                            "access_revision": expected_project_revision,
                        },
                        after_values={
                            "status": PrincipalStatus.RETIRED.value,
                            "access_revision": original.access_revision,
                        },
                        correlation_id=original.operation_id.value,
                    )
                )
                self._session.add(
                    ApplicationAccountDeletionResultRow(
                        operation_id=original.operation_id.value,
                        installation_id=original.installation_id.value,
                        organization_id=original.organization_id.value,
                        project_id=original.project_id.value,
                        actor_principal_id=original.actor_principal_id.value,
                        application_principal_id=original.application_principal_id.value,
                        before_revision=expected_project_revision,
                        access_revision=original.access_revision,
                    )
                )
                await self._session.flush()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _require_reservation(self, original: ApplicationAccountDeletionRecordDTO) -> None:
        parent = IdempotencyReservationRow
        route = (
            f"/v1/projects/{original.project_id.value}/application-accounts/"
            f"{original.application_principal_id.value}"
        )
        reservation = await self._session.scalar(
            select(parent.operation_id).where(
                parent.operation_id == original.operation_id.value,
                parent.organization_id == original.organization_id.value,
                parent.project_id == original.project_id.value,
                parent.principal_id == original.actor_principal_id.value,
                parent.method == HttpMethod.DELETE.value,
                parent.requested_route == route,
                parent.state == OperationReservationState.IN_PROGRESS,
                parent.replay_kind.is_(None),
                parent.expires_at.is_(None),
                parent.lookup_authority_family.is_(None),
                parent.lookup_action_id.is_(None),
            )
        )
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if reservation is None or installed != original.installation_id.value:
            raise ConflictError("Application retirement has no matching reservation binding.")
        actor = await self._session.scalar(
            select(PrincipalRow.id)
            .join(ProjectMembershipRow, ProjectMembershipRow.principal_id == PrincipalRow.id)
            .where(
                PrincipalRow.id == original.actor_principal_id.value,
                PrincipalRow.organization_id == original.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
                ProjectMembershipRow.organization_id == original.organization_id.value,
                ProjectMembershipRow.project_id == original.project_id.value,
                ProjectMembershipRow.principal_kind == PrincipalKind.HUMAN,
            )
        )
        if actor is None:
            raise ConflictError("Application retirement changed the checked actor binding.")

    async def _retire_account(
        self,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> PrincipalStatus:
        organization = original.organization_id.value
        project = original.project_id.value
        application = original.application_principal_id.value
        account = ApplicationAccountRow
        principal = PrincipalRow
        observed = (
            (
                await self._session.execute(
                    select(account.resource_name, principal.status)
                    .join(principal, principal.id == account.principal_id)
                    .where(
                        account.principal_id == application,
                        account.organization_id == organization,
                        account.project_id == project,
                        account.principal_kind == PrincipalKind.APPLICATION,
                        principal.organization_id == organization,
                        principal.kind == PrincipalKind.APPLICATION,
                    )
                )
            )
            .tuples()
            .one_or_none()
        )
        if observed is None or observed[1] not in (
            PrincipalStatus.ACTIVE,
            PrincipalStatus.SUSPENDED,
        ):
            raise ConflictError("The checked application account cannot be retired.")
        name, previous = observed
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None or checked_at.utcoffset() is None or checked_at > now:
            raise RuntimeError("Application retirement changed the checked database time.")
        advanced = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == project,
                ProjectRow.organization_id == organization,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == expected_project_revision,
            )
            .values(access_revision=original.access_revision)
            .returning(ProjectRow.access_revision)
        )
        if advanced is None:
            raise StaleRevisionError()
        retired = await self._session.scalar(
            update(principal)
            .where(
                principal.id == application,
                principal.organization_id == organization,
                principal.kind == PrincipalKind.APPLICATION,
                principal.status == previous,
            )
            .values(status=PrincipalStatus.RETIRED)
            .returning(principal.id)
        )
        if retired is None:
            raise ConflictError("The checked application account changed during retirement.")
        key = ApplicationKeyRow
        await self._session.execute(
            update(key)
            .where(
                key.application_principal_id == application,
                key.organization_id == organization,
                key.project_id == project,
                key.installation_id == original.installation_id.value,
                key.revoked_at.is_(None),
            )
            .values(revoked_at=checked_at)
        )
        if name is not None:
            reserved = ApplicationAccountNameReservationRow
            retired_name = await self._session.scalar(
                update(reserved)
                .where(
                    reserved.project_id == project,
                    reserved.organization_id == organization,
                    reserved.application_principal_id == application,
                    reserved.name == name,
                    reserved.retired.is_(False),
                )
                .values(retired=True)
                .returning(reserved.name)
            )
            if retired_name is None:
                raise ConflictError("Application retirement changed the permanent Name binding.")
        return previous

    async def _remove_relationships(self, original: ApplicationAccountDeletionRecordDTO) -> None:
        project = original.project_id.value
        application = original.application_principal_id.value
        await self._session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project,
                ProjectActionGrantRow.recipient_principal_id == application,
            )
        )
        await self._session.execute(
            delete(GroupActionGrantRow).where(
                GroupActionGrantRow.project_id == project,
                GroupActionGrantRow.recipient_principal_id == application,
            )
        )
        await self._session.execute(
            delete(ModelConnectionActionGrantRow).where(
                ModelConnectionActionGrantRow.project_id == project,
                ModelConnectionActionGrantRow.recipient_principal_id == application,
            )
        )
        await self._session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.project_id == project,
                ApplicationActionGrantRow.application_principal_id == application,
            )
        )
        await self._session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == project,
                GroupManagerRow.principal_id == application,
            )
        )
        await self._session.execute(
            delete(GroupMembershipRow).where(
                GroupMembershipRow.project_id == project,
                GroupMembershipRow.principal_id == application,
            )
        )
        await self._session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.organization_id == original.organization_id.value,
                ProjectMembershipRow.project_id == project,
                ProjectMembershipRow.principal_id == application,
                ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
            )
        )
