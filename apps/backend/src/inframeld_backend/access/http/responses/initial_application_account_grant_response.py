from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.http.responses.application_account_grant_target_response import (
    ApplicationAccountGrantTargetResponse,
)


class InitialApplicationAccountGrantResponse(BaseModel):
    target: ApplicationAccountGrantTargetResponse
    action_id: ApplicationAccountAction = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")
