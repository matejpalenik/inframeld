import asyncio
import math
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)


class HumanAccessTokenAuthenticationService(HumanAccessTokenAuthenticator):
    """Verify an access token matches a human identity that can be resolved."""

    def __init__(
        self,
        token_verifier: HumanAccessTokenVerifier,
        identity_verifier: HumanIdentityVerifier,
        reader: HumanIdentityLinkReader,
        *,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:

        for seconds in (provider_timeout_seconds, total_timeout_seconds):
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Authentication timeouts must be finite and positive.")

        self._token_verifier = token_verifier
        self._identity_verifier = identity_verifier
        self._reader = reader
        self._provider_timeout_seconds = provider_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

    def _provider_budget(self, deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError()

        return min(self._provider_timeout_seconds, remaining)

    @override
    async def authenticate(
        self,
        credential: HumanAccessTokenCredential | None,
    ) -> AccessContextDTO:

        if credential is None:
            raise AuthenticationRequiredError

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout_seconds

        try:
            async with asyncio.timeout_at(deadline):
                # Verify token in Hydra
                identity = await self._token_verifier.verify(
                    credential, timeout_seconds=self._provider_budget(deadline)
                )

                if identity is None:
                    raise AuthenticationRequiredError

                # Verify the identity in the access token matches Kratos
                current_identity = await self._identity_verifier.verify(
                    identity, timeout_seconds=self._provider_budget(deadline)
                )

                if current_identity is None or current_identity != identity:
                    raise AuthenticationRequiredError

                # Find the principal identity in the DB
                principal = await self._reader.find_principal(current_identity)

                if principal is None or not HumanAuthenticationPolicy.may_authenticate(principal):
                    raise AccessDeniedError

                if loop.time() >= deadline:
                    raise TimeoutError

                return AccessContextDTO(actor_principal_id=principal.id)
        except TimeoutError as error:
            raise DependencyUnavailableError from error
