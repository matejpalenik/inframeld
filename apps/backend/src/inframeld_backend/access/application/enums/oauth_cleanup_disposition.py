from enum import StrEnum


class OAuthCleanupDisposition(StrEnum):
    NOT_NEEDED = "not_needed"
    RETRYABLE = "retryable"
    OPERATOR_REQUIRED = "operator_required"
