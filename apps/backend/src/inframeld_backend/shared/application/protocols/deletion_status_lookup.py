from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)


class DeletionStatusLookup(Protocol):
    """Read retained facts only for the currently eligible original initiating human.

    Missing, expired and nonmatching bindings are uniformly unresolved. Invalid
    authoritative observations or unavailable dependencies remain failures. Reads
    do not slide expiry, admit deletion, or authorize continuation/restoration.
    """

    @abstractmethod
    async def lookup(
        self, *, access: AccessContextDTO, query: GetDeletionStatusQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO: ...
