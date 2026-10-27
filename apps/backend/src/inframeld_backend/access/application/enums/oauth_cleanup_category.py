from enum import StrEnum


class OAuthCleanupCategory(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    RATE_LIMITED = "rate_limited"
    TRANSPORT_FAILURE = "transport_failure"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_REJECTION = "provider_rejection"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
