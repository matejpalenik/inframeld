"""Define the transport-neutral base for application operation failures."""

from typing import ClassVar

from inframeld_backend.shared.application.enums.application_error_code import ApplicationErrorCode


class ApplicationError(Exception):
    """Represent a deliberate application-layer operation failure.

    This exception is transport-neutral. Only explicitly supported concrete
    subclasses receive public HTTP, MCP, or worker mappings. The message is
    diagnostic and must not be exposed by default.

    Attributes:
        code: Stable semantic category used by diagnostics and mappings.
        message: Developer-authored diagnostic explanation.
    """

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.APPLICATION_ERROR

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
