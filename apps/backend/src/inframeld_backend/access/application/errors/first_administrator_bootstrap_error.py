from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode,
)


class FirstAdministratorBootstrapError(Exception):
    def __init__(self, code: FirstAdministratorBootstrapErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
