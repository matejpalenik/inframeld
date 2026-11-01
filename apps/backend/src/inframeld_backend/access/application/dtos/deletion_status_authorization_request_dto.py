from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class DeletionStatusAuthorizationRequestDTO:
    """Identify the original operation whose retained outcome is requested."""

    operation_id: OperationId
