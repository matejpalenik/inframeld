from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class InvitationProjectMembershipIntentDTO:
    project_id: ProjectId
    kind: Literal[InvitationAssignmentKind.PROJECT_MEMBERSHIP] = (
        InvitationAssignmentKind.PROJECT_MEMBERSHIP
    )
