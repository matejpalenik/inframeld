from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_assignment_facts_dto import (
    InvitationAssignmentFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationIssuerFactsDTO:
    """Observe retained issuer account authority without presenting an issuer credential."""

    organization_access: OrganizationAccessFactsDTO
    has_coherent_identity: bool
    assignments: tuple[InvitationAssignmentFactsDTO, ...]
