import asyncio
from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_admission_result_reader import (
    HumanAdmissionResultReader,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_admission_operation_result_row import (
    HumanAdmissionOperationResultRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresHumanAdmissionResultReader(HumanAdmissionResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanAdmissionResultDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Admission replay requires the active caller transaction.")
        if operation.replay_kind is not OperationReplayKind.SAFE_RESULT:
            raise ConflictError("The original admission result is unavailable.")
        parent, result = IdempotencyReservationRow, HumanAdmissionOperationResultRow
        try:
            async with asyncio.timeout(5):
                row = await self._session.scalar(
                    select(result)
                    .join(parent, parent.operation_id == result.operation_id)
                    .where(
                        result.operation_id == operation.operation_id.value,
                        result.installation_id == installation_id.value,
                        result.authority == identity.authority.value,
                        result.subject == identity.subject.value,
                        result.organization_id == organization_id.value,
                        result.actor_principal_id == actor_id.value,
                        parent.organization_id == result.organization_id,
                        parent.principal_id == result.actor_principal_id,
                        parent.project_id.is_(None),
                        parent.method == "POST",
                        parent.requested_route
                        == f"/v1/organizations/{organization_id.value}/human-admissions",
                        parent.lookup_authority_family == "organization_action_use",
                        parent.lookup_action_id == OrganizationAction.ADMIT_USERS.value,
                        parent.state == OperationReservationState.REPLAYABLE,
                        parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                        parent.expires_at == operation.expires_at,
                        parent.expires_at > func.clock_timestamp(),
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            raise ConflictError("The original admission result is unavailable.")
        if (
            row.before_revision < 0
            or row.access_revision != row.before_revision + int(row.changed)
            or row.status_code != (201 if row.changed else 200)
        ):
            raise ConflictError("The original admission result is incoherent.")
        return HumanAdmissionResultDTO(
            installation_id,
            identity,
            organization_id,
            actor_id,
            PrincipalId(row.principal_id),
            row.access_revision,
            row.changed,
            operation,
        )
