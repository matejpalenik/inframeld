from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction


class ModelConnectionActionGrantItemResponse(BaseModel):
    model_connection_id: UUID = Field(serialization_alias="modelConnectionId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: ModelConnectionAction = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
