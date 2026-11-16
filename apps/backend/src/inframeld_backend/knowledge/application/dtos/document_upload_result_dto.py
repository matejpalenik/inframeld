from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class DocumentUploadResultDTO:
    """The original safe admission references, without read or storage authority."""

    operation_id: OperationId
    project_id: ProjectId
    document_id: DocumentId
    version_id: DocumentVersionId
    idempotency_expires_at: datetime | None = None

    def matches_original(self, other: "DocumentUploadResultDTO") -> bool:
        """Compare the identities assigned before the receipt deadline exists."""
        return (self.operation_id, self.project_id, self.document_id, self.version_id) == (
            other.operation_id,
            other.project_id,
            other.document_id,
            other.version_id,
        )
