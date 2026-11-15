from enum import StrEnum


class DocumentUploadState(StrEnum):
    PENDING = "pending"
    ADMITTED = "admitted"
    UNUSED = "unused"
