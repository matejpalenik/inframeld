from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.domain.enums.invitation_target_kind import InvitationTargetKind


class InvitationEmbeddingProfileTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    kind: Literal[InvitationTargetKind.EMBEDDING_PROFILE]
    embedding_profile_id: UUID = Field(alias="embeddingProfileId")
