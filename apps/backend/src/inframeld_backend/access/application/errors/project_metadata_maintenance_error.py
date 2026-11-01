from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode,
)


class ProjectMetadataMaintenanceError(Exception):
    def __init__(self, code: ProjectMetadataMaintenanceErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
