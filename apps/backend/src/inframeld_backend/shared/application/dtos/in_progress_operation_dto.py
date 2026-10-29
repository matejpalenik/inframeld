from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class InProgressOperationDTO:
    """Identify retained synchronous processing without inventing a background job."""

    operation_id: OperationId
