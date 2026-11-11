from dataclasses import dataclass
from typing import cast

from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId


@dataclass(frozen=True, slots=True)
class DocumentSourceId:
    """Identify the exact selected Document and immutable version pair."""

    document_id: DocumentId
    version_id: DocumentVersionId

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.document_id), DocumentId) or not isinstance(
            cast(object, self.version_id), DocumentVersionId
        ):
            raise TypeError("A source requires typed Document and version identifiers.")
