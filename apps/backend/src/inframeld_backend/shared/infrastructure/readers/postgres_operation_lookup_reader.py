from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class PostgresOperationLookupReader(OperationLookupReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OperationReservationResultDTO | None:
        return None
