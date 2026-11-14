from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)


class ProcessingProfileActionGrantItemResponse(BaseModel):
    processing_profile_id: UUID = Field(serialization_alias="processingProfileId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: ProcessingProfileAction = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
