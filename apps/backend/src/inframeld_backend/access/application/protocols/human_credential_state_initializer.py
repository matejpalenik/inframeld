from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class HumanCredentialStateInitializer(Protocol):
    """Initialize security metadata for a subject read from a trusted Hydra challenge.

    This never admits an account, grants access or advances an existing version.
    Coordinate the exact identity before reading or creating version state.
    Finish that short READ COMMITTED transaction before browser verification.
    """

    @abstractmethod
    async def initialize(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        """Return current state, refusing a missing version with existing recovery history."""
        ...
