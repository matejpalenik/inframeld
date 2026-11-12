import asyncio
import math
from json import JSONDecodeError
from time import monotonic
from typing import override
from uuid import UUID

from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_response import ApiResponse
from ory_kratos_client.exceptions import ApiException, OpenApiException
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.human_session_cleanup_outcome_dto import (
    HumanSessionCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_session_revoker import HumanSessionRevoker
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority


class KratosHumanSessionRevoker(HumanSessionRevoker):
    """Use one original deadline for one exact identity SDK call.

    Bootstrap owns the SDK pool with retries/debug disabled. An SDK thread may
    finish after cancellation or timeout. No provider outcome authorizes another call.
    """

    def __init__(self, client: IdentityApi, authority: IdentityAuthority) -> None:
        self._client = client
        self._authority = authority

    @override
    async def revoke_sessions(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> HumanSessionCleanupOutcomeDTO:
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("The provider timeout must be finite and positive.")
        if identity.authority != self._authority:
            raise ValueError("The identity does not match the configured provider.")
        try:
            UUID(identity.subject.value)
        except (TypeError, ValueError):
            raise ValueError("Session cleanup requires the exact provider identity ID.") from None
        deadline = monotonic() + timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await asyncio.to_thread(self._send, identity, deadline)
                if monotonic() >= deadline:
                    observed = self._unconfirmed(
                        response.status_code if isinstance(response, ApiResponse) else None
                    )
                    return HumanSessionCleanupOutcomeDTO(
                        IdentityRecoveryCleanupState.UNCERTAIN, observed.http_status
                    )
                if isinstance(response, ApiResponse):
                    if response.status_code == 204 and response.raw_data == b"":
                        return HumanSessionCleanupOutcomeDTO(
                            IdentityRecoveryCleanupState.CONFIRMED, 204
                        )
                    return self._unconfirmed(response.status_code)
        except ApiException as error:
            # Private SDK bodies and exception text must not enter the result.
            status: object = getattr(error, "status", None)
            observed = self._unconfirmed(status)
            if monotonic() >= deadline:
                return HumanSessionCleanupOutcomeDTO(
                    IdentityRecoveryCleanupState.UNCERTAIN, observed.http_status
                )
            return observed
        except (
            TimeoutError,
            HTTPError,
            OpenApiException,
            ValidationError,
            JSONDecodeError,
            UnicodeDecodeError,
        ):
            pass
        return self._unconfirmed(None)

    def _send(self, identity: VerifiedHumanIdentityDTO, deadline: float) -> object:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError
        return self._client.delete_identity_sessions_with_http_info(
            id=identity.subject.value, _request_timeout=remaining
        )

    @staticmethod
    def _unconfirmed(status: object) -> HumanSessionCleanupOutcomeDTO:
        safe_status = status if type(status) is int and 100 <= status <= 599 else None
        state = (
            IdentityRecoveryCleanupState.FAILED
            if safe_status is not None and 400 <= safe_status <= 499 and safe_status != 408
            else IdentityRecoveryCleanupState.UNCERTAIN
        )
        return HumanSessionCleanupOutcomeDTO(state, safe_status)
