from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.http.responses.embedding_profile_definition_response import (
    EmbeddingProfileDefinitionResponse,
)


class EmbeddingProfileResponse(BaseModel):
    """Describe saved vector meaning and its intended logical layout."""

    project_id: UUID = Field(serialization_alias="projectId")
    embedding_profile_id: UUID = Field(serialization_alias="embeddingProfileId")
    name: str
    display_name: str = Field(serialization_alias="displayName")
    definition: EmbeddingProfileDefinitionResponse
    vector_index_id: UUID = Field(serialization_alias="vectorIndexId")
    vector_layout_id: UUID = Field(serialization_alias="vectorLayoutId")
    placement_version: int = Field(serialization_alias="placementVersion", ge=1, le=1)
    shard_count: int = Field(serialization_alias="shardCount", ge=2, le=2)
