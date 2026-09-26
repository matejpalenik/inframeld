"""Define transport-neutral application failure categories shared by features."""

from typing import ClassVar

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.application.application_error_code import ApplicationErrorCode


class InvalidInputError(ApplicationError):
    """Raised when parsed input violates a use-case precondition."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.INVALID_INPUT

    def __init__(self, message: str = "The supplied input is invalid for this operation.") -> None:
        super().__init__(message)


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested resource is unavailable to the operation."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.RESOURCE_NOT_FOUND

    def __init__(self, message: str = "The requested resource is not available.") -> None:
        super().__init__(message)


class AccessDeniedError(ApplicationError):
    """Raised when authorization denies an application operation."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.ACCESS_DENIED

    def __init__(self, message: str = "The requested action is not permitted.") -> None:
        super().__init__(message)


class ConflictError(ApplicationError):
    """Raised when an operation conflicts with current application state."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.CONFLICT

    def __init__(self, message: str = "The operation conflicts with the current state.") -> None:
        super().__init__(message)


class DependencyUnavailableError(ApplicationError):
    """Raised for a recognized availability failure in a required dependency.

    This classification does not imply that retrying is safe or that external
    work did not complete.
    """

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.DEPENDENCY_UNAVAILABLE

    def __init__(self, message: str = "A required dependency is temporarily unavailable.") -> None:
        super().__init__(message)


class AuthenticationRequiredError(ApplicationError):
    """Reject a missing or invalid human credential without revealing its contents."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.AUTHENTICATION_REQUIRED

    def __init__(self) -> None:
        super().__init__("Authentication is required.")
