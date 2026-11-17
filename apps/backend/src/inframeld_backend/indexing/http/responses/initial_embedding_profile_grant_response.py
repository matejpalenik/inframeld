from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.indexing.domain.enums.embedding_profile_action import (
    EmbeddingProfileAction,
)
from inframeld_backend.indexing.http.responses.embedding_profile_grant_target_response import (
    EmbeddingProfileGrantTargetResponse,
)


class InitialEmbeddingProfileGrantResponse(BaseModel):
    target: EmbeddingProfileGrantTargetResponse
    action_id: EmbeddingProfileAction = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")
