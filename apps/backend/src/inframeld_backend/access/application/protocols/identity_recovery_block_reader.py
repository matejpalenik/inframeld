from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class IdentityRecoveryBlockReader(Protocol):
    """Read recovery blocks independently of local account admission."""

    @abstractmethod
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        """Return whether this installation has an unreleased block for the identity.

        Use the exact authority and subject supplied by a trusted verifier.
        A block remains active until explicitly released, including when both
        provider outcomes are confirmed. A local principal does not need to exist.

        Each call owns a short, independent read session and supports concurrent
        callers. Do not cache results, create accounts, or change cleanup state.
        Missing installation metadata and recognized database availability
        failures raise DependencyUnavailableError. Unexpected failures propagate.
        """
        ...
