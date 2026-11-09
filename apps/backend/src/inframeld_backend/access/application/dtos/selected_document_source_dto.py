from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId


@dataclass(frozen=True, slots=True)
class SelectedDocumentSourceDTO:
    """Trusted producer observation of one selected version, not caller input."""

    source_id: DocumentSourceId
    is_live: bool
