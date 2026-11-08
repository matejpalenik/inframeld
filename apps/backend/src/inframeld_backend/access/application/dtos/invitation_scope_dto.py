from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO


@dataclass(frozen=True, slots=True)
class InvitationScopeDTO:
    """Present one authoritative intended scope, never a caller-selected label."""

    target: InvitationTargetDTO
    display_name: str
