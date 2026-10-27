import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import override

from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_request_dto import (
    HumanOAuthConsentRequestDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.oauth_consent_decision import OAuthConsentDecision
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_credential_state_initializer import (
    HumanCredentialStateInitializer,
)
from inframeld_backend.access.application.protocols.human_credential_state_reader import (
    HumanCredentialStateReader,
)
from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.protocols.identity_recovery_block_reader import (
    IdentityRecoveryBlockReader,
)
from inframeld_backend.access.application.protocols.oauth_consent_decision_writer import (
    OAuthConsentDecisionWriter,
)
from inframeld_backend.access.application.protocols.oauth_consent_request_reader import (
    OAuthConsentRequestReader,
)
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.policies.human_oauth_consent_policy import (
    HumanOAuthConsentPolicy,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)


class HumanOAuthConsentService(HumanOAuthConsentHandler):
    def __init__(
        self,
        reader: OAuthConsentRequestReader,
        writer: OAuthConsentDecisionWriter,
        verifier: BrowserSessionVerifier,
        recovery_blocks: IdentityRecoveryBlockReader,
        *,
        credential_states: HumanCredentialStateReader,
        credential_initializer: HumanCredentialStateInitializer,
        authority: IdentityAuthority,
        api_audience: HumanAPIAudience,
        remember_consent_seconds: int = 3600,
        provider_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        for seconds in (provider_timeout_seconds, total_timeout_seconds):
            if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Consent timeouts must be finite and positive.")
        if type(remember_consent_seconds) is not int or remember_consent_seconds <= 0:
            raise ValueError("Remembered consent must have a positive whole duration.")
        self._credential_states = credential_states
        self._credential_initializer = credential_initializer
        self._reader = reader
        self._writer = writer
        self._verifier = verifier
        self._recovery_blocks = recovery_blocks
        self._authority = authority
        self._api_audience = api_audience
        self._remember_consent_seconds = remember_consent_seconds
        self._provider_timeout_seconds = provider_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def inspect(
        self, *, credential: BrowserSessionCredential, query: InspectHumanOAuthConsentQuery
    ) -> HumanOAuthConsentDetailsDTO:
        deadline = asyncio.get_running_loop().time() + self._total_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                request, identity = await self._check_read_only_request(
                    credential, query.challenge, deadline
                )
                return HumanOAuthConsentDetailsDTO(
                    identity=identity,
                    client_id=request.client_id,
                    installation=self._api_audience,
                    scopes=request.scopes,
                    audiences=request.audiences,
                    approval_required=not request.skip,
                    remember_consent_seconds=self._remember_consent_seconds,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def decide(
        self, *, credential: BrowserSessionCredential, command: DecideHumanOAuthConsentCommand
    ) -> OAuthConsentContinuationDTO:
        deadline = asyncio.get_running_loop().time() + self._total_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                if command.decision is OAuthConsentDecision.DENY:
                    await self._check_read_only_request(credential, command.challenge, deadline)
                    return await self._provider_call(
                        lambda timeout: self._writer.deny(
                            command.challenge, timeout_seconds=timeout
                        ),
                        deadline,
                    )
                request, binding = await self._prepare_approval(
                    credential, command.challenge, deadline
                )
                remember_for = (
                    self._remember_consent_seconds
                    if command.remember and not request.skip
                    else None
                )
                return await self._provider_call(
                    lambda timeout: self._writer.allow(
                        command.challenge,
                        binding=binding,
                        scopes=request.scopes,
                        audiences=request.audiences,
                        remember_for_seconds=remember_for,
                        timeout_seconds=timeout,
                    ),
                    deadline,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def _provider_call[Result](
        self, operation: Callable[[float], Awaitable[Result]], deadline: float
    ) -> Result:
        loop = asyncio.get_running_loop()
        provider_deadline = min(deadline, loop.time() + self._provider_timeout_seconds)
        remaining = provider_deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError
        async with asyncio.timeout_at(provider_deadline):
            result = await operation(remaining)
        if loop.time() >= provider_deadline:
            raise TimeoutError
        return result

    async def _read_supported_request(
        self, challenge: OAuthConsentChallenge, deadline: float
    ) -> HumanOAuthConsentRequestDTO:
        request = await self._provider_call(
            lambda timeout: self._reader.read(challenge, timeout_seconds=timeout), deadline
        )
        if not HumanOAuthConsentPolicy.supports_requested_access(
            client_id=request.client_id.value,
            scopes=request.scopes,
            audiences=request.audiences,
            expected_audience=self._api_audience,
        ):
            raise AccessDeniedError()
        return request

    async def _verify_browser_identity(
        self,
        credential: BrowserSessionCredential,
        request: HumanOAuthConsentRequestDTO,
        deadline: float,
    ) -> VerifiedHumanIdentityDTO:
        identity = await self._provider_call(
            lambda _timeout: self._verifier.verify(credential), deadline
        )
        if identity is None:
            raise AuthenticationRequiredError()
        if identity.authority != self._authority or identity.subject != request.subject:
            raise AccessDeniedError()
        return identity

    async def _check_read_only_request(
        self,
        credential: BrowserSessionCredential,
        challenge: OAuthConsentChallenge,
        deadline: float,
    ) -> tuple[HumanOAuthConsentRequestDTO, VerifiedHumanIdentityDTO]:
        request = await self._read_supported_request(challenge, deadline)
        identity = await self._verify_browser_identity(credential, request, deadline)
        blocked = await self._recovery_blocks.is_blocked(identity)
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
        if not HumanOAuthConsentPolicy.may_approve(
            client_id=request.client_id.value,
            scopes=request.scopes,
            audiences=request.audiences,
            expected_audience=self._api_audience,
            has_pending_recovery=blocked,
        ):
            raise AccessDeniedError()
        return request, identity

    async def _prepare_approval(
        self,
        credential: BrowserSessionCredential,
        challenge: OAuthConsentChallenge,
        deadline: float,
    ) -> tuple[HumanOAuthConsentRequestDTO, HumanOAuthCredentialBindingDTO]:
        request = await self._read_supported_request(challenge, deadline)
        initial = await self._credential_initializer.initialize(
            VerifiedHumanIdentityDTO(self._authority, request.subject)
        )
        identity = await self._verify_browser_identity(credential, request, deadline)
        current = await self._credential_states.read(identity)
        if (
            initial.identity != identity
            or current.identity != identity
            or initial.installation_id != current.installation_id
            or initial.version is None
            or current.version != initial.version
        ):
            raise AccessDeniedError()
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
        if not HumanOAuthConsentPolicy.may_approve(
            client_id=request.client_id.value,
            scopes=request.scopes,
            audiences=request.audiences,
            expected_audience=self._api_audience,
            has_pending_recovery=initial.has_pending_recovery or current.has_pending_recovery,
        ):
            raise AccessDeniedError()
        return request, HumanOAuthCredentialBindingDTO(
            identity, initial.installation_id, initial.version
        )
