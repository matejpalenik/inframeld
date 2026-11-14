from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class InvitationScopeDTO:
    """Present one authoritative intended scope, never a caller-selected label."""

    target: InvitationTargetDTO
    display_name: str
    model_project_id: ProjectId | None = None
