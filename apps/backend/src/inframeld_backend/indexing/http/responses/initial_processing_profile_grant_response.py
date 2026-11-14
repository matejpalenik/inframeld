from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.http.responses.processing_profile_grant_target_response import (
    ProcessingProfileGrantTargetResponse,
)


class InitialProcessingProfileGrantResponse(BaseModel):
    target: ProcessingProfileGrantTargetResponse
    action_id: ProcessingProfileAction = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")
