import asyncio
import math
from json import JSONDecodeError
from time import monotonic
from typing import override

from ory_hydra_client import OAuth2Api
from ory_hydra_client.api_response import ApiResponse
from ory_hydra_client.exceptions import ApiException, OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.value_objects.oauth_consent_request_id import (
    OAuthConsentRequestId,
)
from inframeld_backend.access.application.value_objects.oauth_login_session_id import (
    OAuthLoginSessionId,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


class HydraHumanOAuthCredentialRevoker(HumanOAuthCredentialRevoker):
    """Use Hydra's private SDK with exact targets and one bounded attempt.

    The caller owns the SDK client/pool, with retries and debug logging disabled.
    The SDK thread may finish after timeout or cancellation. Only an empty 204
    confirms cleanup, including Hydra's acknowledgement of an already removed
    target. Other 4xx responses are rejections, not proof of absence.
    """

    def __init__(self, client: OAuth2Api) -> None:
        self._client = client

    def _send(self, target: OAuthConsentRequestId | OAuthLoginSessionId, deadline: float) -> object:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError

        if isinstance(target, OAuthConsentRequestId):
            # The pinned Hydra release emits consent UUIDs without hyphens.
            return self._client.revoke_o_auth2_consent_sessions_with_http_info(
                consent_request_id=target.value.hex, _request_timeout=remaining
            )
        return self._client.revoke_o_auth2_login_sessions_with_http_info(
            sid=str(target.value), _request_timeout=remaining
        )

    async def _revoke(
        self, target: OAuthConsentRequestId | OAuthLoginSessionId, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")

        deadline = monotonic() + timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await asyncio.to_thread(self._send, target, deadline)
                if monotonic() >= deadline:
                    raise TimeoutError
                if (
                    isinstance(response, ApiResponse)
                    and response.status_code == 204
                    and response.raw_data == b""
                ):
                    return IdentityRecoveryCleanupState.CONFIRMED
        except ApiException as error:
            # SDK exception members are untyped. Never retain their sensitive body.
            status: object = getattr(error, "status", None)
            if isinstance(status, int) and 400 <= status < 500:
                return IdentityRecoveryCleanupState.FAILED
        except (
            OpenApiException,
            HTTPError,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
            TimeoutError,
        ):
            pass
        return IdentityRecoveryCleanupState.UNCERTAIN

    @override
    async def revoke_grant(
        self, consent_request_id: OAuthConsentRequestId, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        return await self._revoke(consent_request_id, timeout_seconds)

    @override
    async def revoke_login(
        self, login_session_id: OAuthLoginSessionId, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        return await self._revoke(login_session_id, timeout_seconds)
