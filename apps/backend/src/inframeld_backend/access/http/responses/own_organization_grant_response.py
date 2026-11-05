from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.organization_action import OrganizationAction


class OwnOrganizationGrantResponse(BaseModel):
    action_id: OrganizationAction = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
