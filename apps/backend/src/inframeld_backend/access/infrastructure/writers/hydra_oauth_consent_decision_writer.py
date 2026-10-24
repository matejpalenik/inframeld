import asyncio
import math
from json import JSONDecodeError
from time import monotonic
from typing import override
from urllib.parse import parse_qs, urlsplit

from ory_hydra_client import OAuth2Api
from ory_hydra_client.exceptions import ApiException, OpenApiException
from ory_hydra_client.models.accept_o_auth2_consent_request import AcceptOAuth2ConsentRequest
from ory_hydra_client.models.accept_o_auth2_consent_request_session import (
    AcceptOAuth2ConsentRequestSession,
)
from ory_hydra_client.models.o_auth2_redirect_to import OAuth2RedirectTo
from ory_hydra_client.models.reject_o_auth2_request import RejectOAuth2Request
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.protocols.oauth_consent_decision_writer import (
    OAuthConsentDecisionWriter,
)
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)


class HydraOAuthConsentDecisionWriter(OAuthConsentDecisionWriter):
    """Use bounded SDK threads without following provider redirects or retrying writes.

    A cancelled or timed-out SDK thread may still finish remotely. The lifespan
    owns the injected SDK client, with retries and debug output disabled.
    """

    def __init__(self, client: OAuth2Api, *, public_url: str) -> None:
        parsed = urlsplit(public_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Expected a trusted public Hydra base URL.")
        self._client = client
        self._authorization_url = urlsplit(public_url.rstrip("/") + "/oauth2/auth")

    def _send(
        self,
        challenge: OAuthConsentChallenge,
        payload: AcceptOAuth2ConsentRequest | None,
        deadline: float,
    ) -> object:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError
        if payload is None:
            return self._client.reject_o_auth2_consent_request(
                consent_challenge=challenge.value,
                reject_o_auth2_request=RejectOAuth2Request(error="access_denied"),
                _request_timeout=remaining,
            )
        return self._client.accept_o_auth2_consent_request(
            consent_challenge=challenge.value,
            accept_o_auth2_consent_request=payload,
            _request_timeout=remaining,
        )

    async def _decide(
        self,
        challenge: OAuthConsentChallenge,
        payload: AcceptOAuth2ConsentRequest | None,
        timeout_seconds: float,
    ) -> OAuthConsentContinuationDTO:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")
        deadline = monotonic() + timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await asyncio.to_thread(self._send, challenge, payload, deadline)
                if monotonic() >= deadline:
                    raise TimeoutError
        except ApiException as error:
            status: object = getattr(error, "status", None)
            if status in (400, 404, 410):
                raise ResourceNotFoundError("The consent request is not available.") from None
            raise DependencyUnavailableError() from None
        except (
            OpenApiException,
            HTTPError,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            TimeoutError,
        ):
            raise DependencyUnavailableError() from None
        if not isinstance(response, OAuth2RedirectTo):
            raise DependencyUnavailableError()
        try:
            parsed = urlsplit(response.redirect_to)
            verifier = parse_qs(parsed.query).get("consent_verifier", [])
            if (
                (parsed.scheme, parsed.netloc, parsed.path)
                != (
                    self._authorization_url.scheme,
                    self._authorization_url.netloc,
                    self._authorization_url.path,
                )
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
                or len(verifier) != 1
                or not verifier[0]
                or any(
                    character.isspace() or ord(character) < 32 for character in response.redirect_to
                )
            ):
                raise ValueError
        except ValueError:
            raise DependencyUnavailableError() from None
        return OAuthConsentContinuationDTO(response.redirect_to)

    @override
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
        if remember_for_seconds is not None and (
            type(remember_for_seconds) is not int or remember_for_seconds <= 0
        ):
            raise ValueError("Remembered consent must have a positive whole duration.")
        return await self._decide(
            challenge,
            AcceptOAuth2ConsentRequest(
                session=AcceptOAuth2ConsentRequestSession(
                    access_token={
                        "inframeld_installation_id": str(binding.installation_id.value),
                        "inframeld_credential_version": binding.version.value,
                    }
                ),
                grant_scope=[scope.value for scope in scopes],
                grant_access_token_audience=[audience.value for audience in audiences],
                remember=remember_for_seconds is not None,
                remember_for=remember_for_seconds,
            ),
            timeout_seconds,
        )

    @override
    async def deny(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> OAuthConsentContinuationDTO:
        return await self._decide(challenge, None, timeout_seconds)
