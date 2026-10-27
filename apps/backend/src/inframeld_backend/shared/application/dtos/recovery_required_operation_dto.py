from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class RecoveryRequiredOperationDTO:
    """Keep the original operation identity when no safe replay outcome is established."""

    operation_id: OperationId
