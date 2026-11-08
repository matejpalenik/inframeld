from typing import Literal

from pydantic import BaseModel, ConfigDict

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)


class InvitationAdmissionOnlyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    kind: Literal[InvitationAssignmentKind.ADMISSION_ONLY]
