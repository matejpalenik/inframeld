from uuid import UUID

from pydantic import BaseModel, Field


class AccessGroupActionGrantItemResponse(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    access_group_id: UUID = Field(serialization_alias="accessGroupId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: str = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
