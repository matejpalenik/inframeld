from dataclasses import dataclass, field

from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.pipelines.domain.enums.pipeline_reranker import PipelineReranker
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineConfiguration:
    """Carry one complete set of explicitly saved Pipeline settings."""

    collection_id: CollectionId
    processing_profile_id: ProcessingProfileId
    embedding_profile_id: EmbeddingProfileId
    model_connection_id: ModelConnectionId
    model_alias: str
    prompt: str = field(repr=False)
    reranker: PipelineReranker
    top_k: int
    max_passages: int
    generation: GenerationModelSettingsDTO

    def __post_init__(self) -> None:
        RevisionValidation.require(self.top_k)
        RevisionValidation.require(self.max_passages)
        if not 0 < self.max_passages <= self.top_k:
            raise ValueError("Retrieval requires positive limits and max passages at most top K.")
        if self.reranker is not PipelineReranker.NONE:
            raise ValueError("This Pipeline configuration requires no reranker.")
        if (
            self.generation.role is not ModelRole.GENERATION
            or self.generation.temperature is not None
            or self.generation.structured_output is not False
        ):
            raise ValueError(
                "This Pipeline configuration requires provider-default plain generation."
            )
        for value in (self.model_alias, self.prompt):
            if not value.strip() or "\x00" in value:
                raise ValueError("The selected model and prompt require nonempty text.")
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("The selected model and prompt require UTF-8 text.") from None
