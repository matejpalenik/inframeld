from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.shared.application.errors.job_errors import UnsupportedJobPayloadError
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class PipelinePdfPreparationInput:
    """Freeze the reviewed inputs of one private PDF preparation."""

    collection_id: CollectionId
    collection_revision_id: CollectionRevisionId
    configuration_revision: int
    processing_profile_id: ProcessingProfileId
    source: DocumentSourceId

    KIND: ClassVar[str] = "pipeline_pdf_preparation"
    VERSION: ClassVar[int] = 1

    def to_payload(self) -> JobPayload:
        RevisionValidation.require(self.configuration_revision)
        if self.configuration_revision == 0:
            raise ValueError("A saved configuration revision must be positive.")
        data = b"".join(
            (
                self.collection_id.value.bytes,
                self.collection_revision_id.value.bytes,
                self.configuration_revision.to_bytes(8, "big"),
                self.processing_profile_id.value.bytes,
                self.source.document_id.value.bytes,
                self.source.version_id.value.bytes,
            )
        )
        return JobPayload(self.KIND, self.VERSION, data)

    @classmethod
    def from_payload(cls, payload: JobPayload) -> "PipelinePdfPreparationInput":
        data = payload.data
        if (payload.kind, payload.version) != (cls.KIND, cls.VERSION) or len(data) != 88:
            raise UnsupportedJobPayloadError("The PDF preparation capture is unsupported.")

        revision = int.from_bytes(data[32:40], "big")
        if not 1 <= revision <= RevisionValidation.MAX_VALUE:
            raise UnsupportedJobPayloadError("The captured configuration revision is invalid.")
        return cls(
            collection_id=CollectionId(UUID(bytes=data[:16])),
            collection_revision_id=CollectionRevisionId(UUID(bytes=data[16:32])),
            configuration_revision=revision,
            processing_profile_id=ProcessingProfileId(UUID(bytes=data[40:56])),
            source=DocumentSourceId(
                DocumentId(UUID(bytes=data[56:72])),
                DocumentVersionId(UUID(bytes=data[72:])),
            ),
        )
