from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class RecoveryMaintenanceInputError(ValueError):
    """Keep only a safely parsed correlation ID when rejecting host input."""

    def __init__(self, operation_id: OperationId | None = None) -> None:
        super().__init__("Invalid maintenance input.")
        self.operation_id = operation_id
