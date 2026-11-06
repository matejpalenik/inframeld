from typing import override

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.access_group_deletion_binding_reader import (
    AccessGroupDeletionBindingReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)


class PostgresAccessGroupDeletionBindingReader(AccessGroupDeletionBindingReader):
    """Find retained original identity independently of ordinary idempotency lifetime."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def find(
        self,
        *,
        authorization: DeletionRecoveryAuthorizationDTO,
        query: LookupOriginalOperationQuery,
    ) -> OperationId | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Group deletion recovery requires the active caller transaction.")
        binding = DeletionStatusBindingRow
        try:
            rows = (
                await self._session.scalars(
                    select(binding.operation_id)
                    .join(
                        DeletionStatusObservationRow,
                        DeletionStatusObservationRow.operation_id == binding.operation_id,
                    )
                    .where(
                        binding.installation_id == authorization.installation_id.value,
                        binding.organization_id == authorization.organization_id.value,
                        binding.initiator_principal_id == authorization.principal_id.value,
                        binding.project_id == query.project_id.value
                        if query.project_id is not None
                        else binding.project_id.is_(None),
                        binding.method == query.method,
                        binding.requested_route == query.requested_route,
                        binding.request_key == query.key.value,
                        binding.authority_family == "access_group_deletion",
                        binding.action_id == "delete-access-group",
                    )
                    .limit(2)
                )
            ).all()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return OperationId(rows[0]) if len(rows) == 1 else None
