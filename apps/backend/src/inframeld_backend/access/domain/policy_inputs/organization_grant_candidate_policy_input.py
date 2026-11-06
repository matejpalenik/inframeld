from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class OrganizationGrantCandidatePolicyInput:
    """Observe a potential remaining grantor of one exact Organization action."""

    principal: Principal
    has_pending_recovery: bool
    has_coherent_identity: bool
    can_grant: bool
