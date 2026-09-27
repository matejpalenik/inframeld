"""Define transport-neutral application failure categories shared by features."""

from typing import ClassVar

from inframeld_backend.shared.application.enums.application_error_code import ApplicationErrorCode
from inframeld_backend.shared.application.errors.application_error import (
    ApplicationError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class InvalidInputError(ApplicationError):
    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.INVALID_INPUT

    def __init__(self, message: str = "The supplied input is invalid for this operation.") -> None:
        super().__init__(message)


class ResourceNotFoundError(ApplicationError):
    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.RESOURCE_NOT_FOUND

    def __init__(self, message: str = "The requested resource is not available.") -> None:
        super().__init__(message)


class AccessDeniedError(ApplicationError):
    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.ACCESS_DENIED

    def __init__(self, message: str = "The requested action is not permitted.") -> None:
        super().__init__(message)


class ConflictError(ApplicationError):
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
    """Reject missing or invalid credentials; the HTTP boundary returns a generic 401."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.AUTHENTICATION_REQUIRED

    def __init__(self) -> None:
        super().__init__("Authentication is required.")


class IdempotencyKeyReusedError(ConflictError):
    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.IDEMPOTENCY_KEY_REUSED

    def __init__(
        self,
        message: str = "The idempotency key was already used for a different request.",
    ) -> None:
        super().__init__(message)


class IdempotencyInProgressError(ConflictError):
    """Identify an unfinished original operation and when its caller may check again."""

    code: ClassVar[ApplicationErrorCode] = ApplicationErrorCode.IDEMPOTENCY_IN_PROGRESS

    def __init__(
        self,
        operation_id: OperationId,
        retry_after_seconds: int,
        message: str = "The original operation is still in progress.",
    ) -> None:
        if type(retry_after_seconds) is not int or retry_after_seconds < 1:
            raise ValueError("Retry delay must be a positive whole number of seconds.")

        self.operation_id = operation_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)
