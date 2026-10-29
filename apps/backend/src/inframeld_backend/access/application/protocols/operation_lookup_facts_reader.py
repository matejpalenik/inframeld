from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.operation_lookup_facts_dto import (
    OperationLookupFactsDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OperationLookupFactsReader(Protocol):
    """Read current principal, original scope and expected-action grant facts."""

    @abstractmethod
    async def read(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> OperationLookupFactsDTO | None:
        """Use one request-local session and no reservation history or provider I/O.

        Missing current scope returns None. Missing installation metadata and
        recognized dependency failures raise DependencyUnavailableError.
        """
        ...
