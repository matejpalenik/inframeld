import asyncio
import math
from json import JSONDecodeError
from time import monotonic
from typing import override

from ory_hydra_client import OAuth2Api
from ory_hydra_client.exceptions import ApiException, OpenApiException
from ory_hydra_client.models.o_auth2_consent_request import OAuth2ConsentRequest
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.human_oauth_consent_request_dto import (
    HumanOAuthConsentRequestDTO,
)
from inframeld_backend.access.application.protocols.oauth_consent_request_reader import (
    OAuthConsentRequestReader,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)


class HydraOAuthConsentRequestReader(OAuthConsentRequestReader):
    """Read through the lifespan-owned SDK, with retries and debug output disabled."""

    def __init__(self, client: OAuth2Api) -> None:
        self._client = client

    def _read(self, challenge: OAuthConsentChallenge, deadline: float) -> object:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError
        return self._client.get_o_auth2_consent_request(
            consent_challenge=challenge.value, _request_timeout=remaining
        )

    @override
    async def read(
        self, challenge: OAuthConsentChallenge, *, timeout_seconds: float
    ) -> HumanOAuthConsentRequestDTO:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")
        deadline = monotonic() + timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await asyncio.to_thread(self._read, challenge, deadline)
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
        if not isinstance(response, OAuth2ConsentRequest) or (
            response.challenge != challenge.value
            or response.client is None
            or response.client.client_id is None
            or response.subject is None
            or response.requested_scope is None
            or response.requested_access_token_audience is None
            or response.skip is None
        ):
            raise DependencyUnavailableError()
        if response.client.skip_consent:
            raise AccessDeniedError()
        try:
            scopes = tuple(HumanOAuthScope(value) for value in response.requested_scope)
        except ValueError:
            raise AccessDeniedError() from None
        try:
            return HumanOAuthConsentRequestDTO(
                subject=IdentitySubject(response.subject),
                client_id=OAuthClientId(response.client.client_id),
                scopes=scopes,
                audiences=tuple(
                    HumanAPIAudience(value) for value in response.requested_access_token_audience
                ),
                skip=response.skip,
            )
        except ValueError:
            raise DependencyUnavailableError() from None
