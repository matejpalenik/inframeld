from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OperationLookupReader(Protocol):
    """Read one exact original identity and immutable authority binding after authorization."""

    @abstractmethod
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OperationReservationResultDTO | None:
        """Return retained metadata or no authoritative match without changing history.

        Caller authorizes the expected guard first. Missing, mismatched, expired
        and insufficiently bound history are indistinguishable. Actual dependency
        failures propagate as failures. Never reserve, delete, repair or redispatch.
        """
        ...
