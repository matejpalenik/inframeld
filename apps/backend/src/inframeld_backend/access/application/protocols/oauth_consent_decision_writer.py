from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience


class OAuthConsentDecisionWriter(Protocol):
    """Submit a checked human decision through Hydra's private API.

    The caller must verify the current browser identity, exact requested access
    and recovery state first. Calls return only a checked Hydra continuation.
    DependencyUnavailableError can mean approval completed without a usable
    response - do not automatically retry. No database transaction is held.
    """

    @abstractmethod
    async def allow(
        self,
        challenge: OAuthConsentChallenge,
        *,
        scopes: tuple[HumanOAuthScope, ...],
        audiences: tuple[HumanAPIAudience, ...],
        remember_for_seconds: int | None,
        binding: HumanOAuthCredentialBindingDTO,
        timeout_seconds: float,
    ) -> OAuthConsentContinuationDTO:
        """Approve checked access - None means do not record a new remembered approval."""
        ...

    @abstractmethod
    async def deny(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> OAuthConsentContinuationDTO: ...
