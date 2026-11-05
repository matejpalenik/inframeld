from enum import StrEnum


class ObjectStorageAddressingStyle(StrEnum):
    """Select the supported S3 addressing style for the configured endpoint."""

    PATH = "path"
    VIRTUAL = "virtual"
