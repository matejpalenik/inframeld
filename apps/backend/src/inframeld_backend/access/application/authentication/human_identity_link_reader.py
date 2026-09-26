"""Define the HumanIdentityLinkReader application boundary."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.principal import Principal


class HumanIdentityLinkReader(Protocol):
    """Read the local principal linked to this exact verified identity pair."""

    @abstractmethod
    async def find_principal(self, identity: VerifiedHumanIdentity) -> Principal | None:
        """Read the local principal linked to this exact verified identity pair.

        Return `None` when the link is absent. Return account kind and status as
        stored so the application can apply its admission policy. This operation
        reads current state without creating accounts or matching email addresses.

        The identity must come from a trusted verifier. Each lookup owns an
        independent short read session and must support concurrent callers.
        Return detached domain values, never an ORM object or a session.
        Unexpected persistence failures propagate to the caller's error boundary.
        """
        ...
