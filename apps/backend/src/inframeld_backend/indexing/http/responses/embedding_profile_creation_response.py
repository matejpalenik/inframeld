from datetime import datetime

from pydantic import BaseModel, Field

from inframeld_backend.indexing.http.responses.embedding_profile_response import (
    EmbeddingProfileResponse,
)
from inframeld_backend.indexing.http.responses.initial_embedding_profile_grant_response import (
    InitialEmbeddingProfileGrantResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class EmbeddingProfileCreationResponse(BaseModel):
    profile: EmbeddingProfileResponse
    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_access_revision: int = Field(
        serialization_alias="projectAccessRevision",
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    initial_grants: tuple[InitialEmbeddingProfileGrantResponse, ...] = Field(
        serialization_alias="initialGrants", min_length=2, max_length=2
    )
