from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class ProjectDepartureCandidatePolicyInput:
    """Describe one other human's current relationship to an exact responsibility."""

    principal: Principal
    has_pending_recovery: bool
    is_project_member: bool
    has_coherent_identity: bool
    can_grant: bool
    is_group_member: bool
    is_group_manager: bool
