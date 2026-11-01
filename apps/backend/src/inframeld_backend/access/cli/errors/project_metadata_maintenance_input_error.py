from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectMetadataMaintenanceInputError(ValueError):
    def __init__(self, operation_id: OperationId | None = None) -> None:
        self.operation_id = operation_id
        super().__init__("Invalid protected maintenance input.")
