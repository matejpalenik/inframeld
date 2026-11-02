from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class FirstAdministratorBootstrapFactsDTO:
    """Observe admission facts after the identity and installation turns."""

    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO
    credential_state: HumanCredentialStateDTO
    principal: Principal | None
    has_business_state: bool
    has_bootstrap_claim: bool
    observed_at: datetime
