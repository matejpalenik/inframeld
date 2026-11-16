from dataclasses import dataclass

from inframeld_backend.indexing.domain.value_objects.vector_index_id import VectorIndexId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingProfileDTO:
    """Carry the saved definition and exact intended shard references."""

    name: ResourceName
    display_name: SubmittedDisplayName
    reviewed: ReviewedModelSettingsDTO
    vector_index_id: VectorIndexId
    layout: VectorShardLayout
    shard_names: tuple[str, str]

    def has_coherent_layout(self) -> bool:
        """Check the retained shard references against the saved placement version."""
        return (
            self.reviewed.selection.project_id == self.layout.project_id
            and self.layout.shard_count == 2
            and self.shard_names == (self.layout.collection_name(0), self.layout.collection_name(1))
        )
