from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.protocols.organization_action_grant_result_reader import (
    OrganizationActionGrantResultReader,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_operation_result_row import (
    OrganizationActionGrantOperationResultRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresOrganizationActionGrantResultReader(OrganizationActionGrantResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        facts: OrganizationGrantManagementFactsDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Organization grant replay requires the active caller transaction.")
        if operation.replay_kind is not OperationReplayKind.SAFE_RESULT:
            raise ConflictError("The original Organization grant receipt is unavailable.")
        expected_method = (
            HttpMethod.PUT
            if isinstance(command, SetOrganizationActionGrantCommand)
            else HttpMethod.DELETE
        )
        result, parent = OrganizationActionGrantOperationResultRow, IdempotencyReservationRow
        try:
            row = await self._session.scalar(
                select(result)
                .join(parent, parent.operation_id == result.operation_id)
                .where(
                    result.operation_id == operation.operation_id.value,
                    result.installation_id == facts.installation_id.value,
                    result.organization_id == facts.organization_id.value,
                    result.actor_principal_id == facts.actor.id.value,
                    result.recipient_principal_id == command.recipient_principal_id.value,
                    result.action_id == command.action_id.value,
                    result.method == expected_method,
                    parent.principal_id == result.actor_principal_id,
                    parent.organization_id == result.organization_id,
                    parent.project_id.is_(None),
                    parent.method == context.method,
                    parent.requested_route == context.requested_route,
                    parent.request_key == context.key.value,
                    parent.lookup_authority_family
                    == OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ,
                    parent.lookup_action_id == result.action_id,
                    parent.state == OperationReservationState.REPLAYABLE,
                    parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                    parent.expires_at == operation.expires_at,
                    parent.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        expected_level = (
            command.can_grant if isinstance(command, SetOrganizationActionGrantCommand) else None
        )
        if (
            row is None
            or row.before_revision != command.expected_access_revision
            or row.can_grant is not expected_level
            or row.changed != (row.before_can_grant is not row.can_grant)
            or row.access_revision != row.before_revision + int(row.changed)
            or row.status_code
            != (201 if expected_method is HttpMethod.PUT and row.before_can_grant is None else 200)
        ):
            raise ConflictError(
                "The original Organization grant receipt is unavailable or incoherent."
            )
        return OrganizationActionGrantChangeResultDTO(
            installation_id=facts.installation_id,
            organization_id=facts.organization_id,
            actor_principal_id=facts.actor.id,
            recipient_principal_id=command.recipient_principal_id,
            action_id=command.action_id,
            method=expected_method,
            can_grant=row.can_grant,
            access_revision=row.access_revision,
            changed=row.changed,
            status_code=row.status_code,
            operation=operation,
        )
