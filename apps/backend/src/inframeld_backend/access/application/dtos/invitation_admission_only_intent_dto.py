from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.enums.invitation_assignment_kind import (
    InvitationAssignmentKind,
)


@dataclass(frozen=True, slots=True)
class InvitationAdmissionOnlyIntentDTO:
    kind: Literal[InvitationAssignmentKind.ADMISSION_ONLY] = InvitationAssignmentKind.ADMISSION_ONLY
