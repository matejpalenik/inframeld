"""Define transport-neutral application failure categories shared by features."""

from typing import ClassVar

from inframeld_backend.shared.application.application_error import ApplicationError


class InvalidInputError(ApplicationError):
    """Raised when parsed input violates a use-case precondition."""

    code: ClassVar[str] = "invalid_input"

    def __init__(self, message: str = "The supplied input is invalid for this operation.") -> None:
        super().__init__(message)


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested resource is unavailable to the operation."""

    code: ClassVar[str] = "resource_not_found"

    def __init__(self, message: str = "The requested resource is not available.") -> None:
        super().__init__(message)


class AccessDeniedError(ApplicationError):
    """Raised when authorization denies an application operation."""

    code: ClassVar[str] = "access_denied"

    def __init__(self, message: str = "The requested action is not permitted.") -> None:
        super().__init__(message)


class ConflictError(ApplicationError):
    """Raised when an operation conflicts with current application state."""

    code: ClassVar[str] = "conflict"

    def __init__(self, message: str = "The operation conflicts with the current state.") -> None:
        super().__init__(message)


class DependencyUnavailableError(ApplicationError):
    """Raised for a recognized availability failure in a required dependency.

    This classification does not imply that retrying is safe or that external
    work did not complete.
    """

    code: ClassVar[str] = "dependency_unavailable"

    def __init__(self, message: str = "A required dependency is temporarily unavailable.") -> None:
        super().__init__(message)
