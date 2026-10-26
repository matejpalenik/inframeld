import asyncio
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from json import JSONDecodeError
from time import monotonic
from typing import Literal, cast, override

from ory_hydra_client import OAuth2Api
from ory_hydra_client.api_response import ApiResponse
from ory_hydra_client.exceptions import ApiException, OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError, MaxRetryError, ResponseError

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
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
    ) -> HumanOAuthCleanupOutcomeDTO:
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
                    return HumanOAuthCleanupOutcomeDTO(
                        IdentityRecoveryCleanupState.CONFIRMED,
                        OAuthCleanupDisposition.NOT_NEEDED,
                        OAuthCleanupCategory.ACKNOWLEDGED,
                        204,
                    )
                if isinstance(response, ApiResponse):
                    return self._http_outcome(response.status_code, response.headers)
        except ApiException as error:
            # SDK exception members are untyped. Never retain their sensitive body.
            status: object = getattr(error, "status", None)
            return self._http_outcome(status, getattr(error, "headers", None))
        except TimeoutError:
            return HumanOAuthCleanupOutcomeDTO(
                IdentityRecoveryCleanupState.UNCERTAIN,
                OAuthCleanupDisposition.RETRYABLE,
                OAuthCleanupCategory.PROVIDER_TIMEOUT,
            )
        except MaxRetryError as error:
            if isinstance(error.reason, ResponseError):
                return HumanOAuthCleanupOutcomeDTO(
                    IdentityRecoveryCleanupState.UNCERTAIN,
                    OAuthCleanupDisposition.OPERATOR_REQUIRED,
                    OAuthCleanupCategory.PROVIDER_PROTOCOL_ERROR,
                )
            return HumanOAuthCleanupOutcomeDTO(
                IdentityRecoveryCleanupState.UNCERTAIN,
                OAuthCleanupDisposition.RETRYABLE,
                OAuthCleanupCategory.TRANSPORT_FAILURE,
            )
        except HTTPError:
            return HumanOAuthCleanupOutcomeDTO(
                IdentityRecoveryCleanupState.UNCERTAIN,
                OAuthCleanupDisposition.RETRYABLE,
                OAuthCleanupCategory.TRANSPORT_FAILURE,
            )
        except (OpenApiException, ValidationError, JSONDecodeError, UnicodeDecodeError):
            pass

        return HumanOAuthCleanupOutcomeDTO(
            IdentityRecoveryCleanupState.UNCERTAIN,
            OAuthCleanupDisposition.OPERATOR_REQUIRED,
            OAuthCleanupCategory.PROVIDER_PROTOCOL_ERROR,
        )

    @staticmethod
    def _http_outcome(status: object, headers: object) -> HumanOAuthCleanupOutcomeDTO:
        retry_after = HydraHumanOAuthCredentialRevoker._retry_after(headers)
        if isinstance(status, int) and not isinstance(status, bool):
            if status == 429:
                return HumanOAuthCleanupOutcomeDTO(
                    IdentityRecoveryCleanupState.FAILED,
                    OAuthCleanupDisposition.RETRYABLE,
                    OAuthCleanupCategory.RATE_LIMITED,
                    status,
                    retry_after,
                )

            if status == 408 or (500 <= status <= 599 and status not in {501, 505}):
                return HumanOAuthCleanupOutcomeDTO(
                    IdentityRecoveryCleanupState.UNCERTAIN,
                    OAuthCleanupDisposition.RETRYABLE,
                    OAuthCleanupCategory.PROVIDER_UNAVAILABLE,
                    status,
                    retry_after,
                )

            if 400 <= status <= 499:
                return HumanOAuthCleanupOutcomeDTO(
                    IdentityRecoveryCleanupState.FAILED,
                    OAuthCleanupDisposition.OPERATOR_REQUIRED,
                    OAuthCleanupCategory.PROVIDER_REJECTION,
                    status,
                )

        return HumanOAuthCleanupOutcomeDTO(
            IdentityRecoveryCleanupState.UNCERTAIN,
            OAuthCleanupDisposition.OPERATOR_REQUIRED,
            OAuthCleanupCategory.PROVIDER_PROTOCOL_ERROR,
            status
            if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599
            else None,
        )

    @staticmethod
    def _retry_after(headers: object) -> float | None:
        if not isinstance(headers, Mapping):
            return None

        safe_headers = cast(Mapping[str, object], headers)
        value = next(
            (value for name, value in safe_headers.items() if name.casefold() == "retry-after"),
            None,
        )
        if not isinstance(value, str) or len(value) > 128:
            return None

        try:
            if value.isascii() and value.isdecimal():
                seconds = float(value)
            else:
                at = parsedate_to_datetime(value)
                if at.utcoffset() is None:
                    return None
                seconds = (at - datetime.now(UTC)).total_seconds()
        except (ValueError, OverflowError, TypeError):
            return None

        return seconds if math.isfinite(seconds) and seconds >= 0 else None

    @override
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        return await self._revoke(subject, "cli_grants", timeout_seconds)

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        return await self._revoke(subject, "remembered_logins", timeout_seconds)
