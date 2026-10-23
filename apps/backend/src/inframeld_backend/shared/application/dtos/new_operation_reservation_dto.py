from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class NewOperationReservationDTO:
    """Identify work newly reserved in this transaction, before its effects are saved."""

    operation_id: OperationId
