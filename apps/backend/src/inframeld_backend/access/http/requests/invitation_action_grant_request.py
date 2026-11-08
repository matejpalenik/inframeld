from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.http.types.invitation_target_request import InvitationTargetRequest


class InvitationActionGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    kind: Literal[InvitationAssignmentKind.ACTION_GRANT]
    target: InvitationTargetRequest
    action_id: str = Field(alias="actionId", strict=True, min_length=1, max_length=100)
    can_grant: bool = Field(alias="canGrant", strict=True)

    @field_validator("action_id")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        ActionId(value)
        return value
