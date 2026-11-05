from enum import StrEnum


class DiscoveryTransportProfile(StrEnum):
    """Select the accepted public discovery transport policy."""

    HTTPS = "https"
    MANAGED_LOCAL = "managed-local"
