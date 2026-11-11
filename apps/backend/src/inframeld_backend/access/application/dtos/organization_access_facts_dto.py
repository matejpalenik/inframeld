from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class OrganizationAccessFactsDTO:
    """Observe one coherent current actor, Organization revision and stored grants."""

    principal: Principal
    access_revision: int
    grants: tuple[OrganizationActionGrantDTO, ...]
    has_pending_recovery: bool
    oauth_credential_facts: HumanCredentialFactsDTO | None
