from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class GrantRecipientCandidateDTO:
    """Observe one bounded, prefiltered member without authorizing disclosure."""

    principal: Principal
    display_name: str
    is_project_member: bool
    has_pending_recovery: bool
    has_coherent_identity: bool
    application_is_project_bound: bool
