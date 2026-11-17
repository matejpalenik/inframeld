from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import (
    EmbeddingProfileId,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ModelConnectionUsageItemDTO:
    """One saved Embedding Profile reference without provider observations."""

    project_id: ProjectId
    connection_id: ModelConnectionId
    embedding_profile_id: EmbeddingProfileId
    model_alias: str
