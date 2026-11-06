from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationActionGrantItemResponse(BaseModel):
    organization_id: UUID = Field(serialization_alias="organizationId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: str = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
