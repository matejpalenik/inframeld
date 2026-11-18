from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionRevisionDTO:
    """One exact immutable selection and its Collection identity."""

    collection_id: CollectionId
    revision_id: CollectionRevisionId
    version_ids: tuple[DocumentVersionId, ...]
