from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class ProjectDepartureCandidateDTO:
    """Observe another principal's relationship to one exact responsibility."""

    principal: Principal
    has_pending_recovery: bool
    is_project_member: bool
    has_coherent_identity: bool
    can_grant: bool
    is_group_member: bool
    is_group_manager: bool
