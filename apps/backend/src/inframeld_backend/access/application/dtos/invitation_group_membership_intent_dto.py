from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class InvitationGroupMembershipIntentDTO:
    project_id: ProjectId
    access_group_id: AccessGroupId
    kind: Literal[InvitationAssignmentKind.GROUP_MEMBERSHIP] = (
        InvitationAssignmentKind.GROUP_MEMBERSHIP
    )
