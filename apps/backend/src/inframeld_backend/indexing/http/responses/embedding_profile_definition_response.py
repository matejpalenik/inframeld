from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.http.responses.embedding_profile_token_bound_response import (
    EmbeddingProfileTokenBoundResponse,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class EmbeddingProfileDefinitionResponse(BaseModel):
    model_connection_id: UUID = Field(serialization_alias="modelConnectionId")
    model: str
    role: Literal[ModelRole.EMBEDDING]
    dimensions: int = Field(ge=1, le=1536)
    normalization: EmbeddingNormalization
    distance: EmbeddingDistance
    document_prefix: str = Field(serialization_alias="documentPrefix")
    query_prefix: str = Field(serialization_alias="queryPrefix")
    context_tokens: int = Field(
        serialization_alias="contextTokens",
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    expected_provider: str = Field(serialization_alias="expectedProvider")
    expected_model_revision: str | None = Field(serialization_alias="expectedModelRevision")
    token_bound: EmbeddingProfileTokenBoundResponse = Field(serialization_alias="tokenBound")
