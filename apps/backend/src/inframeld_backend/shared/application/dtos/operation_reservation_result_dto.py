from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.enums.operation_replay_kind import (
    OperationReplayKind,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class OperationReservationResultDTO:
    """Carry a low-level reservation result before its stored shape is validated.

    IdempotencyService converts this persistence projection into distinct workflow
    outcomes. Field annotations alone do not validate its state combinations.
    The deadline is absent while work remains active or needs recovery.
    """

    operation_id: OperationId
    created: bool
    state: OperationReservationState
    replay_kind: OperationReplayKind | None
    expires_at: datetime | None
