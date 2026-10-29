import asyncio
from typing import override

from sqlalchemy import Nullable, and_, func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresOperationLookupReader(OperationLookupReader):
    """Observe one retained binding without writing, repairing or extending history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OperationReservationResultDTO | None:
        if query.project_id is None:
            return None
        row = IdempotencyReservationRow
        binding = and_(
            row.principal_id == principal_id.value,
            row.organization_id == query.organization_id.value,
            row.project_id == query.project_id.value,
            row.method == query.method,
            row.requested_route == query.requested_route,
            row.request_key == query.key.value,
            row.lookup_authority_family == query.expected_authority.family.value,
            row.lookup_action_id == query.expected_authority.action_id.value,
            or_(
                row.state != OperationReservationState.REPLAYABLE,
                row.expires_at.is_(None),
                row.expires_at > func.clock_timestamp(),
            ),
        )
        statement = (
            select(
                InstallationIdentityRow.installation_id,
                Nullable(row.operation_id),
                Nullable(row.state),
                Nullable(row.replay_kind),
                Nullable(row.expires_at),
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(row, binding)
            .where(InstallationIdentityRow.singleton_key == 1)
        )
        try:
            async with asyncio.timeout(5.0):
                observed = (await self._session.execute(statement)).tuples().one_or_none()
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, LookupError):
            raise DependencyUnavailableError() from None
        if observed is None:
            raise DependencyUnavailableError()

        installed, operation_id, state, replay_kind, expiry = observed
        if installed != query.installation_id.value or operation_id is None:
            return None
        if state is None:
            raise DependencyUnavailableError()
        return OperationReservationResultDTO(
            OperationId(operation_id), False, state, replay_kind, expiry
        )
