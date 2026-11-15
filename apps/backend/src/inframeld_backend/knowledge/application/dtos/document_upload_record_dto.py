from dataclasses import dataclass

from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.knowledge.application.enums.document_upload_state import DocumentUploadState
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO


@dataclass(frozen=True, slots=True)
class DocumentUploadRecordDTO:
    """Bind one pending Document slot to its original storage attempt."""

    result: DocumentUploadResultDTO
    allocation: ArtifactAllocationDTO
    state: DocumentUploadState
    created: bool = False
