from pydantic import BaseModel, Field

from inframeld_backend.access.http.types.invitation_target_request import InvitationTargetRequest


class InvitationScopeResponse(BaseModel):
    target: InvitationTargetRequest
    display_name: str = Field(serialization_alias="displayName")
