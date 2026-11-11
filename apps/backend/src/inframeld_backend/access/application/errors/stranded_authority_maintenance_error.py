from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode,
)


class StrandedAuthorityMaintenanceError(Exception):
    def __init__(self, code: StrandedAuthorityMaintenanceErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
