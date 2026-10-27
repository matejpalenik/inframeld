from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanCredentialStateDTO:
    """Observe one identity's version and recovery block together. None means uninitialized."""

    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO
    version: HumanCredentialVersion | None
    has_pending_recovery: bool
