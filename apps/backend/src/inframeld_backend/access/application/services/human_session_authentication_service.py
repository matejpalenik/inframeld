"""Orchestrate bounded provider verification and current local human admission."""

import asyncio
import math
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)


class HumanSessionAuthenticationService(HumanSessionAuthenticator):
    """Verify a browser cookie and admit an active local human before the deadline."""

    def __init__(
        self,
        verifier: BrowserSessionVerifier,
        reader: HumanIdentityLinkReader,
        *,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        for seconds in (provider_timeout_seconds, total_timeout_seconds):
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Authentication timeouts must be finite and positive.")

        self._verifier = verifier
        self._reader = reader
        self._provider_timeout_seconds = provider_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout_seconds

        try:
            async with asyncio.timeout_at(deadline):
                provider_deadline = min(
                    deadline,
                    loop.time() + self._provider_timeout_seconds,
                )
                async with asyncio.timeout_at(provider_deadline):
                    identity = await self._verifier.verify(credential)

                # A dependency might return after swallowing cancellation.
                # Its late result cannot establish either success or rejection.
                if loop.time() >= provider_deadline:
                    raise TimeoutError()

                if identity is None:
                    raise AuthenticationRequiredError()

                principal = await self._reader.find_principal(identity)

                if loop.time() >= deadline:
                    raise TimeoutError()

                if principal is None or not HumanAuthenticationPolicy.may_authenticate(principal):
                    raise AccessDeniedError()

                return AccessContextDTO(actor_principal_id=principal.id)
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
