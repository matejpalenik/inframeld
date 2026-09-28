"""Reserve operation identities within a caller-owned transaction."""

from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class OperationReservationWriter(Protocol):
    """Find or create reservations without committing the caller's transaction."""

    @abstractmethod
    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        """Return the original operation for an equal request; reject changed input."""
        ...

    @abstractmethod
    async def mark_replayable(
        self,
        operation_id: OperationId,
        replay_kind: OperationReplayKind,
    ) -> datetime | None:
        """Record a safe replay outcome in the caller's transaction."""
        ...
