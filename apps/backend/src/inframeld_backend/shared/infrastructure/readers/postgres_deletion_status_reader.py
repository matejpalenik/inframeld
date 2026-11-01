import asyncio
from typing import override

from sqlalchemy import DateTime, Nullable, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_projection_reader import (
    DeletionStatusProjectionReader,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_deletion_status_mapper import (
    PostgresDeletionStatusMapper,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)


class PostgresDeletionStatusReader(DeletionStatusProjectionReader):
    """Read exact retained initiator scope within the caller's coordinated transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion status requires an active caller transaction.")

        binding = DeletionStatusBindingRow
        statement = (
            select(
                binding,
                Nullable(DeletionStatusObservationRow),
                func.clock_timestamp(type_=DateTime(timezone=True)),
            )
            .select_from(binding)
            .outerjoin(
                DeletionStatusObservationRow,
                DeletionStatusObservationRow.operation_id == binding.operation_id,
            )
            .where(
                binding.operation_id == authorization.operation_id.value,
                binding.installation_id == authorization.installation_id.value,
                binding.organization_id == authorization.organization_id.value,
                binding.initiator_principal_id == authorization.principal_id.value,
            )
            .execution_options(populate_existing=True)
        )
        try:
            async with asyncio.timeout(5):
                stored = (await self._session.execute(statement)).tuples().one_or_none()
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, LookupError):
            raise DependencyUnavailableError() from None
        if stored is None:
            return None

        retained, owner, observed_at = stored
        try:
            return PostgresDeletionStatusMapper.to_observation(retained, owner, observed_at)
        except (TypeError, ValueError, LookupError):
            raise DependencyUnavailableError() from None
