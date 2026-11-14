from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.http.enums.processing_profile_target_kind import (
    ProcessingProfileTargetKind,
)


class ProcessingProfileGrantTargetResponse(BaseModel):
    kind: Literal[ProcessingProfileTargetKind.PROCESSING_PROFILE]
    processing_profile_id: UUID = Field(serialization_alias="processingProfileId")
