from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.operation_lookup_facts_dto import (
    OperationLookupFactsDTO,
)
from inframeld_backend.access.application.protocols.operation_lookup_facts_reader import (
    OperationLookupFactsReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class PostgresOperationLookupFactsReader(OperationLookupFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> OperationLookupFactsDTO | None:
        return None
