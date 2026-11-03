from typing import Literal

from pydantic import BaseModel, Field


class OwnOrganizationGrantResponse(BaseModel):
    action_id: Literal["admit-users", "suspend-users", "restore-users", "create-projects"] = Field(
        serialization_alias="actionId"
    )
    can_grant: bool = Field(serialization_alias="canGrant")
