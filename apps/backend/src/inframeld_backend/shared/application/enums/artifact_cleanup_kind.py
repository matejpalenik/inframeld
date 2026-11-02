from enum import StrEnum


class ArtifactCleanupKind(StrEnum):
    ABANDONED_STAGING = "abandoned_staging"
    ERASURE = "erasure"
    RETENTION_EXPIRY = "retention_expiry"
