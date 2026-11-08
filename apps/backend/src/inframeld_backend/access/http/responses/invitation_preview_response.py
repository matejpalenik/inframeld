from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.invitation_scope_response import (
    InvitationScopeResponse,
)
from inframeld_backend.access.http.types.invitation_assignment_request import (
    InvitationAssignmentRequest,
)


class InvitationPreviewResponse(BaseModel):
    invitation_id: UUID = Field(serialization_alias="invitationId")
    organization_id: UUID = Field(serialization_alias="organizationId")
    assignments: list[InvitationAssignmentRequest]
    expires_at: datetime = Field(serialization_alias="expiresAt")
    scopes: list[InvitationScopeResponse]
