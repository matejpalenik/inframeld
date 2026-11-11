"""Orchestrate bounded provider verification and current local human admission."""

import asyncio
import math
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_authentication_state_dto import (
    HumanAuthenticationStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_identity_link_state import (
    HumanIdentityLinkState,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_credential_state_reader import (
    HumanCredentialStateReader,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
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
        browser_session_verifier: BrowserSessionVerifier,
        credential_state_reader: HumanCredentialStateReader,
        *,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        for seconds in (provider_timeout_seconds, total_timeout_seconds):
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Authentication timeouts must be finite and positive.")

        self._browser_session_verifier = browser_session_verifier
        self._credential_state_reader = credential_state_reader
        self._provider_timeout_seconds = provider_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout_seconds
        provider_deadline = min(deadline, loop.time() + self._provider_timeout_seconds)
        try:
            async with asyncio.timeout_at(deadline):
                identity = await self._verify(credential, provider_deadline)
                if identity is None:
                    raise AuthenticationRequiredError()
                captured = await self._credential_state_reader.read_authentication_state(identity)
                if loop.time() >= deadline:
                    raise TimeoutError
                principal = self._admit(captured)
                initial = captured.credential_state
                if initial.identity != identity:
                    raise AuthenticationRequiredError()
                final_identity = await self._verify(credential, provider_deadline)
                if final_identity != identity:
                    raise AuthenticationRequiredError()
                current = await self._credential_state_reader.read_authentication_state(identity)
                if loop.time() >= deadline:
                    raise TimeoutError
                current_principal = self._admit(current)
                final = current.credential_state
                if (
                    final.identity != initial.identity
                    or final.installation_id != initial.installation_id
                    or final.version != initial.version
                    or current_principal.id != principal.id
                    or current_principal.organization_id != principal.organization_id
                ):
                    raise AuthenticationRequiredError()
                assert initial.version is not None
                return AccessContextDTO(
                    current_principal.id,
                    BrowserSessionAuthenticationDTO(
                        identity, initial.installation_id, initial.version
                    ),
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    async def _verify(
        self, credential: BrowserSessionCredential, deadline: float
    ) -> VerifiedHumanIdentityDTO | None:
        loop = asyncio.get_running_loop()
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError
        async with asyncio.timeout_at(deadline):
            identity = await self._browser_session_verifier.verify(
                credential, timeout_seconds=remaining
            )
        if loop.time() >= deadline:
            raise TimeoutError
        return identity

    @staticmethod
    def _admit(observation: HumanAuthenticationStateDTO) -> Principal:
        if observation.link_state is HumanIdentityLinkState.INCOHERENT:
            raise DependencyUnavailableError()
        if observation.link_state is HumanIdentityLinkState.UNLINKED:
            if observation.linked_principal is not None:
                raise DependencyUnavailableError()
            raise AccessDeniedError()
        principal = observation.linked_principal
        state = observation.credential_state
        if principal is None or state.version is None:
            raise DependencyUnavailableError()
        if not HumanAuthenticationPolicy.may_authenticate(
            PrincipalAccessPolicyInput(principal, state.has_pending_recovery, True)
        ):
            raise AccessDeniedError()
        return principal
