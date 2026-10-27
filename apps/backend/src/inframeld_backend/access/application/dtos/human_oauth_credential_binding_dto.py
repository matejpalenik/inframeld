from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanOAuthCredentialBindingDTO:
    """Bind a Hydra grant to an identity and credential generation, not permissions."""

    identity: VerifiedHumanIdentityDTO
    installation_id: InstallationId
    version: HumanCredentialVersion
