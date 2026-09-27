from dataclasses import dataclass

from inframeld_backend.shared.application.enums.operation_replay_kind import (
    OperationReplayKind,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class OperationReservationResultDTO:
    """Identify the operation and its recorded replay decision."""

    operation_id: OperationId
    created: bool
    state: OperationReservationState
    replay_kind: OperationReplayKind | None
