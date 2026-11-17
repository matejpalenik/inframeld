from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EmbeddingProfileGrantTargetResponse(BaseModel):
    kind: Literal["embedding-profile"]
    embedding_profile_id: UUID = Field(serialization_alias="embeddingProfileId")
