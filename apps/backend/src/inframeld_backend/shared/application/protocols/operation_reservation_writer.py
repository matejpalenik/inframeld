"""Reserve operation identities within a caller-owned transaction."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)


class OperationReservationWriter(Protocol):
    """Find or create a reservation without committing the caller's transaction"""

    @abstractmethod
    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        """Return the original operation for an equal request - reject changed input."""
        ...
