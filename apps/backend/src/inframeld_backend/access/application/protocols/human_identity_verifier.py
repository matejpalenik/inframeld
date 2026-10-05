from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class HumanIdentityVerifier(Protocol):
    """Check the identity provider's current state for an already verified subject."""

    @abstractmethod
    async def verify(
        self,
        identity: VerifiedHumanIdentityDTO,
        *,
        timeout_seconds: float,
    ) -> VerifiedHumanIdentityDTO | None:
        """Return the same identity only when it currently exists and is eligible.

        Use the configured provider - do not use email matching or caller-selected URLs to verify identity.

        Return `None` for a missing or ineligible identity.

        Raise `DependencyUnavailableError` for unavailable or malformed verification.

        Bound provider I/O by `timeout_seconds` and cache no success.
        """
        ...
