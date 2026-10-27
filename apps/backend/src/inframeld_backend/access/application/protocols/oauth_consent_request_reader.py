from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_oauth_consent_request_dto import (
    HumanOAuthConsentRequestDTO,
)
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)


class OAuthConsentRequestReader(Protocol):
    """Read the account and access Hydra is asking a human to approve.

    Returned data is provider evidence, not permission to approve. Missing or
    expired challenges raise ResourceNotFoundError. Unavailable or malformed
    provider responses raise DependencyUnavailableError.
    """

    @abstractmethod
    async def read(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> HumanOAuthConsentRequestDTO: ...
