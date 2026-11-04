from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanAdmissionFactsDTO:
    """Observe fresh actor and exact recipient facts after identity and Org turns."""

    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO
    actor: OrganizationAccessFactsDTO
    principal: Principal | None
    credential_state: HumanCredentialStateDTO
    has_credential_history: bool
