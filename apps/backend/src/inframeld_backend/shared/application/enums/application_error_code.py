"""Name the application failure categories independently of HTTP representations."""

from enum import StrEnum


class ApplicationErrorCode(StrEnum):
    """Identify reviewed internal failure categories without exposing diagnostic text."""

    APPLICATION_ERROR = "application_error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_INPUT = "invalid_input"
    RESOURCE_NOT_FOUND = "resource_not_found"
    ACCESS_DENIED = "access_denied"
    CONFLICT = "conflict"
    STALE_REVISION = "stale_revision"
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    IDEMPOTENCY_IN_PROGRESS = "idempotency_in_progress"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
