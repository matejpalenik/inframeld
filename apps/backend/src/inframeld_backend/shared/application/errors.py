"""Define transport-neutral application failure categories shared by features."""

from typing import ClassVar

from inframeld_backend.shared.application.application_error import ApplicationError


class InvalidInputError(ApplicationError):
    """Raised when parsed input violates a use-case precondition."""

    code: ClassVar[str] = "invalid_input"


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested resource is unavailable to the operation."""

    code: ClassVar[str] = "resource_not_found"


class AccessDeniedError(ApplicationError):
    """Raised when authorization denies an application operation."""

    code: ClassVar[str] = "access_denied"


class ConflictError(ApplicationError):
    """Raised when an operation conflicts with current application state."""

    code: ClassVar[str] = "conflict"


class DependencyUnavailableError(ApplicationError):
    """Raised for a recognized availability failure in a required dependency.

    This classification does not imply that retrying is safe or that external
    work did not complete.
    """

    code: ClassVar[str] = "dependency_unavailable"
