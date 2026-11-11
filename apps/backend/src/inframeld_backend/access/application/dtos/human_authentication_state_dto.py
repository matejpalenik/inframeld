from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.enums.human_identity_link_state import (
    HumanIdentityLinkState,
)
from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class HumanAuthenticationStateDTO:
    """Observe credential state and the same read's complete local identity link."""

    credential_state: HumanCredentialStateDTO
    link_state: HumanIdentityLinkState
    linked_principal: Principal | None
