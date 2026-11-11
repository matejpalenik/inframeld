from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_authentication_state_dto import (
    HumanAuthenticationStateDTO,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class HumanCredentialStateReader(Protocol):
    """Read committed identity security state without holding a session during provider I/O."""

    @abstractmethod
    async def read(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        """Return version and block in one observation, failing closed on unavailable state."""
        ...

    @abstractmethod
    async def read_authentication_state(
        self, identity: VerifiedHumanIdentityDTO
    ) -> HumanAuthenticationStateDTO:
        """Observe linked-principal and credential facts together before provider work."""
        ...
