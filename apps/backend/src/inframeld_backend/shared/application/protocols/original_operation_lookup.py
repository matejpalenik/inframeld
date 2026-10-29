from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OriginalOperationLookup(Protocol):
    """Observe retained original admission under current independently checked authority."""

    @abstractmethod
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> (
        CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | UnresolvedOperationDTO
    ):
        """Return original metadata without admitting work or certifying payload equivalence.

        Invalid guards, denied authority and unavailable lookup remain failures.
        Unresolved does not establish no effects. Admission is independent of a
        later job state, and no job reference is inferred from operation identity.
        """
        ...
