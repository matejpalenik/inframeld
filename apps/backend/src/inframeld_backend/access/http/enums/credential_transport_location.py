from enum import StrEnum


class CredentialTransportLocation(StrEnum):
    """Advertise the supported location of an API credential."""

    HEADER = "header"
