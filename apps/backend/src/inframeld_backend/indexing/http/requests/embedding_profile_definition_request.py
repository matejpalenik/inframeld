from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)


class EmbeddingProfileDefinitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    model_connection_id: UUID = Field(alias="modelConnectionId")
    model: Literal["text-embedding-3-small"]
    dimensions: int = Field(strict=True, ge=1, le=1536)
    normalization: EmbeddingNormalization
    distance: EmbeddingDistance
    document_prefix: str = Field(alias="documentPrefix", strict=True)
    query_prefix: str = Field(alias="queryPrefix", strict=True)
    context_tokens: int = Field(alias="contextTokens", strict=True, ge=1, le=8191)

    @field_validator("document_prefix", "query_prefix")
    @classmethod
    def _prefix(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("An embedding prefix cannot contain NUL.")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("An embedding prefix must be valid UTF-8.") from None
        return value
