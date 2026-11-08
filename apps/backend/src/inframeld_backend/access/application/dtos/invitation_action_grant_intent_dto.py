from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class InvitationActionGrantIntentDTO:
    target: InvitationTargetDTO
    action_id: ActionId
    can_grant: bool
    kind: Literal[InvitationAssignmentKind.ACTION_GRANT] = InvitationAssignmentKind.ACTION_GRANT
