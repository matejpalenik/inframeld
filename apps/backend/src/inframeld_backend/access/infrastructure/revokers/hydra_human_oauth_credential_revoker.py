import asyncio
import math
from json import JSONDecodeError
from time import monotonic
from typing import Literal, override

from ory_hydra_client import OAuth2Api
from ory_hydra_client.api_response import ApiResponse
from ory_hydra_client.exceptions import ApiException, OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject


class HydraHumanOAuthCredentialRevoker(HumanOAuthCredentialRevoker):
    """Use Hydra's private SDK for one subject-scoped bulk request.

    The caller owns the SDK client/pool, with retries and debug logging disabled.
    The SDK thread may finish after timeout or cancellation. Only an empty 204
    confirms the request, including an already-empty scope. Subject-wide login
    deletion sends no front-channel or back-channel logout notifications.
    """

    def __init__(self, client: OAuth2Api) -> None:
        self._client = client

    def _send(
        self,
        subject: IdentitySubject,
        operation: Literal["cli_grants", "remembered_logins"],
        deadline: float,
    ) -> object:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError

        if operation == "cli_grants":
            return self._client.revoke_o_auth2_consent_sessions_with_http_info(
                subject=subject.value, client="inframeld-cli", _request_timeout=remaining
            )
        return self._client.revoke_o_auth2_login_sessions_with_http_info(
            subject=subject.value, _request_timeout=remaining
        )

    async def _revoke(
        self,
        subject: IdentitySubject,
        operation: Literal["cli_grants", "remembered_logins"],
        timeout_seconds: float,
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
                response = await asyncio.to_thread(self._send, subject, operation, deadline)
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
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        return await self._revoke(subject, "cli_grants", timeout_seconds)

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        return await self._revoke(subject, "remembered_logins", timeout_seconds)
