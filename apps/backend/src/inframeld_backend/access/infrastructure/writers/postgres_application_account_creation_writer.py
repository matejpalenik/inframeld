from typing import override
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.protocols.application_account_creation_writer import (
    ApplicationAccountCreationWriter,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_creation_result_row import (
    ApplicationAccountCreationResultRow,
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
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresApplicationAccountCreationWriter(ApplicationAccountCreationWriter):
    """Persist only the reviewed empty-account admission in its caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create(
        self, *, account: CreatedApplicationAccountDTO, expected_project_revision: int
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Account persistence requires the active caller transaction.")
        actions = [action.value for action in account.initial_actions]
        fixed = [
            ApplicationAccountAction.ISSUE_KEYS.value,
            ApplicationAccountAction.REVOKE_KEYS.value,
            ApplicationAccountAction.DELETE_ACCOUNT.value,
        ]
        RevisionValidation.require(expected_project_revision)
        if (
            actions != fixed
            or account.access_revision != expected_project_revision + 1
            or account.principal_id == account.creator_principal_id
        ):
            raise RuntimeError("Account persistence changed the fixed initial state.")
        RevisionValidation.require(account.access_revision)
        route = f"/v1/projects/{account.project_id.value}/application-accounts"
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.operation_id == account.operation_id.value,
                IdempotencyReservationRow.organization_id == account.organization_id.value,
                IdempotencyReservationRow.project_id == account.project_id.value,
                IdempotencyReservationRow.principal_id == account.creator_principal_id.value,
                IdempotencyReservationRow.method == "POST",
                IdempotencyReservationRow.requested_route == route,
                IdempotencyReservationRow.lookup_authority_family == "project_action_use",
                IdempotencyReservationRow.lookup_action_id
                == ProjectAction.CREATE_APPLICATION_ACCOUNTS.value,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
        )
        if reservation is None:
            raise ConflictError("Account creation has no matching original reservation.")
        human = await self._session.scalar(
            select(PrincipalRow.id)
            .join(ProjectMembershipRow, ProjectMembershipRow.principal_id == PrincipalRow.id)
            .where(
                PrincipalRow.id == account.creator_principal_id.value,
                PrincipalRow.organization_id == account.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
                ProjectMembershipRow.project_id == account.project_id.value,
                ProjectMembershipRow.organization_id == account.organization_id.value,
            )
        )
        if human is None:
            raise ConflictError("The checked account creator is no longer eligible.")
        revision = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == account.project_id.value,
                ProjectRow.organization_id == account.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == expected_project_revision,
                ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
            )
            .values(access_revision=account.access_revision)
            .returning(ProjectRow.access_revision)
        )
        if revision is None:
            raise StaleRevisionError()

        self._session.add(
            PrincipalRow(
                id=account.principal_id.value,
                organization_id=account.organization_id.value,
                kind=PrincipalKind.APPLICATION,
                status=PrincipalStatus.ACTIVE,
                display_name=account.display_name,
            )
        )
        await self._session.flush()
        extension = ApplicationAccountRow(
            principal_id=account.principal_id.value,
            organization_id=account.organization_id.value,
            project_id=account.project_id.value,
            principal_kind=PrincipalKind.APPLICATION,
        )
        self._session.add(extension)
        await self._session.flush()
        allocated = await self._session.scalar(
            insert(ApplicationAccountNameReservationRow)
            .values(
                project_id=account.project_id.value,
                name=account.name.value,
                organization_id=account.organization_id.value,
                application_principal_id=account.principal_id.value,
                retired=False,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ApplicationAccountNameReservationRow.project_id,
                    ApplicationAccountNameReservationRow.name,
                ]
            )
            .returning(ApplicationAccountNameReservationRow.name)
        )
        if allocated is None:
            raise ConflictError("The requested application account Name is unavailable.")
        extension.resource_name = account.name.value
        self._session.add(
            ProjectMembershipRow(
                project_id=account.project_id.value,
                principal_id=account.principal_id.value,
                organization_id=account.organization_id.value,
                principal_kind=PrincipalKind.APPLICATION,
                application_principal_id=account.principal_id.value,
                assigned_by_principal_id=human,
            )
        )
        await self._session.flush()
        for action in actions:
            self._session.add(
                ApplicationActionGrantRow(
                    project_id=account.project_id.value,
                    application_principal_id=account.principal_id.value,
                    recipient_principal_id=human,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action,
                    can_grant=True,
                    assigned_by_principal_id=human,
                )
            )
        self._session.add(
            ApplicationAccountCreationResultRow(
                operation_id=account.operation_id.value,
                organization_id=account.organization_id.value,
                project_id=account.project_id.value,
                principal_id=account.principal_id.value,
                creator_principal_id=human,
                name=account.name.value,
                display_name=account.display_name,
                before_revision=expected_project_revision,
                access_revision=account.access_revision,
                initial_actions=actions,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=account.organization_id.value,
                project_id=account.project_id.value,
                actor_kind="human",
                actor_principal_id=human,
                affected_principal_id=account.principal_id.value,
                event_type="application_account_created",
                target_kind="application_account",
                target_id=account.principal_id.value,
                after_values={
                    "name": account.name.value,
                    "display_name": account.display_name,
                    "creator_principal_id": str(human),
                    "initial_actions": actions,
                    "access_revision": account.access_revision,
                },
                correlation_id=account.operation_id.value,
            )
        )
        await self._session.flush()
