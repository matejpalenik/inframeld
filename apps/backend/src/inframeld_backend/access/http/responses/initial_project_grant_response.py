from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.http.responses.project_grant_target_response import (
    ProjectGrantTargetResponse,
)


class InitialProjectGrantResponse(BaseModel):
    target: ProjectGrantTargetResponse
    action_id: ProjectAction = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")
