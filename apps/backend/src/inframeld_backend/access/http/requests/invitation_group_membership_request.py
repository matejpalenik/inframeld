from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)


class InvitationGroupMembershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    kind: Literal[InvitationAssignmentKind.GROUP_MEMBERSHIP]
    project_id: UUID = Field(alias="projectId")
    access_group_id: UUID = Field(alias="accessGroupId")
