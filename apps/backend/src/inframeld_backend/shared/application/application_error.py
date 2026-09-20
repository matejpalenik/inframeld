from typing import ClassVar


class ApplicationError(Exception):
    """Base class for expected application-layer failures.

    Application errors are safe, intentional failures that can be translated
    into a stable transport response by the HTTP layer.
    """

    code: ClassVar[str] = "application_error"

    def __init__(self, message: str) -> None:
        """Create an application error with a safe human-readable message."""
        self.message = message
        super().__init__(message)
