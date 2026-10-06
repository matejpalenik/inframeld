import asyncio
import math
from datetime import UTC, datetime
from json import JSONDecodeError
from time import monotonic
from typing import override
from uuid import UUID

from ory_hydra_client import IntrospectedOAuth2Token, OAuth2Api
from ory_hydra_client.exceptions import ApiException, OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class HydraAccessTokenVerifier(HumanAccessTokenVerifier):
    """Verify through the injected private SDK client and normalize provider metadata.

    Bootstrap owns the client/pool and configures its host, TLS, disabled retries
    and disabled debug logging. This adapter neither creates local identities
    nor checks Kratos eligibility or product permissions.
    """

    def __init__(
        self, client: OAuth2Api, settings: HydraSettings, kratos_authority: IdentityAuthority
    ) -> None:
        self._client = client
        self._settings = settings
        self._kratos_authority = kratos_authority

    # region Internal helpers
    def _introspect(
        self, credential: HumanAccessTokenCredential, deadline: float
    ) -> IntrospectedOAuth2Token:
        remaining = deadline - monotonic()

        if remaining <= 0:
            raise TimeoutError

        return self._client.introspect_o_auth2_token(
            token=credential.value, scope=self._settings.required_scope, _request_timeout=remaining
        )

    def _read_identity(self, token: object) -> VerifiedHumanIdentityDTO | None:
        # Narrow SDK output here: a null or unexpected body is not confirmation of identity.
        if not isinstance(token, IntrospectedOAuth2Token):
            raise DependencyUnavailableError

        if not token.active:
            return None

        if (
            token.iss is None
            or token.client_id is None
            or token.aud is None
            or token.scope is None
            or token.exp is None
            or token.sub is None
            or token.token_type is None
            or token.token_use is None
        ):
            raise DependencyUnavailableError

        if not all(
            value.strip()
            for value in (
                token.iss,
                token.client_id,
                token.scope,
                token.sub,
                token.token_type,
                token.token_use,
            )
        ):
            raise DependencyUnavailableError

        if (
            token.token_use != "access_token"
            or token.token_type.casefold() != "bearer"
            or token.iss != self._settings.issuer.value
            or token.client_id != self._settings.client_id
            or self._settings.api_audience.value not in token.aud
            or self._settings.required_scope not in token.scope.split(" ")
            or token.obfuscated_subject not in (None, "")
        ):
            return None

        now = datetime.now(UTC).timestamp()

        if (
            token.exp <= now
            or (token.nbf is not None and token.nbf > now)
            or (token.iat is not None and token.iat > now)
        ):
            return None

        try:
            subject = IdentitySubject(str(UUID(token.sub)))
        except ValueError:
            raise DependencyUnavailableError from None

        return VerifiedHumanIdentityDTO(authority=self._kratos_authority, subject=subject)

    # endregion

    @override
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")

        deadline = monotonic() + timeout_seconds

        try:
            async with asyncio.timeout(timeout_seconds):
                token = await asyncio.to_thread(self._introspect, credential, deadline)

                identity = self._read_identity(token)

                if monotonic() >= deadline:
                    raise TimeoutError

                return identity
        except (
            ApiException,
            OpenApiException,
            HTTPError,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            TimeoutError,
        ):
            # We should obscure the bodies of these errors because thye can contain sensitive information.
            raise DependencyUnavailableError from None
