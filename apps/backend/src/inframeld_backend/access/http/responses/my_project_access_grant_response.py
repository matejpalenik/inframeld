from typing import Annotated

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.access_group_grant_target_response import (
    AccessGroupGrantTargetResponse,
)
from inframeld_backend.access.http.responses.application_account_grant_target_response import (
    ApplicationAccountGrantTargetResponse,
)
from inframeld_backend.access.http.responses.project_grant_target_response import (
    ProjectGrantTargetResponse,
)


class MyProjectAccessGrantResponse(BaseModel):
    target: Annotated[
        ProjectGrantTargetResponse
        | AccessGroupGrantTargetResponse
        | ApplicationAccountGrantTargetResponse,
        Field(discriminator="kind"),
    ]
    action_id: str = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
