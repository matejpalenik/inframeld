from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class StrandedAuthorityMaintenanceInputError(ValueError):
    def __init__(self, operation_id: OperationId | None) -> None:
        super().__init__("Invalid maintenance request.")
        self.operation_id = operation_id
