import asyncio
from collections.abc import Iterator
from json import JSONDecodeError
from threading import Event
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.api_response import ApiResponse
from ory_hydra_client.exceptions import ApiException, OpenApiException
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.value_objects.oauth_consent_request_id import (
    OAuthConsentRequestId,
)
from inframeld_backend.access.application.value_objects.oauth_login_session_id import (
    OAuthLoginSessionId,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
    HydraHumanOAuthCredentialRevoker,
)

type Operation = Literal["grant", "login"]
CONSENT = OAuthConsentRequestId(UUID("01234567-89ab-cdef-0123-456789abcdef"))
LOGIN = OAuthLoginSessionId(UUID("abcdef01-2345-6789-abcd-ef0123456789"))
METHODS: dict[Operation, str] = {
    "grant": "revoke_o_auth2_consent_sessions_with_http_info",
    "login": "revoke_o_auth2_login_sessions_with_http_info",
}


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host="http://hydra-admin.test:4445", retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


async def _revoke(
    revoker: HydraHumanOAuthCredentialRevoker, operation: Operation, timeout_seconds: float = 1.0
) -> IdentityRecoveryCleanupState:
    if operation == "grant":
        return await revoker.revoke_grant(CONSENT, timeout_seconds=timeout_seconds)
    return await revoker.revoke_login(LOGIN, timeout_seconds=timeout_seconds)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
async def test_acknowledged_cleanup_sends_only_the_exact_target(
    client: OAuth2Api, operation: Operation
) -> None:
    """Never substitute a subject-wide or client-wide request for one target."""
    response = ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")
    with patch.object(client, METHODS[operation], return_value=response) as revoke:
        assert await _revoke(HydraHumanOAuthCredentialRevoker(client), operation) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

    revoke.assert_called_once()
    arguments = dict(revoke.call_args.kwargs)
    timeout: object = arguments.pop("_request_timeout")
    assert isinstance(timeout, float)
    assert 0 < timeout <= 1.0
    assert arguments == (
        {"consent_request_id": CONSENT.value.hex}
        if operation == "grant"
        else {"sid": str(LOGIN.value)}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429])
async def test_explicit_rejection_is_failed_without_exposing_provider_details(
    client: OAuth2Api, operation: Operation, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.object(
        client, METHODS[operation], side_effect=ApiException(status=status, body="secret-token")
    ) as revoke:
        result = await _revoke(HydraHumanOAuthCredentialRevoker(client), operation)

    assert result == IdentityRecoveryCleanupState.FAILED
    assert "secret-token" not in repr(result) + caplog.text
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
@pytest.mark.parametrize(
    "error",
    [
        ApiException(status=500, body="secret-token"),
        ApiException(status=503, body="secret-token"),
        ApiException(status=None, body="secret-token"),
        HTTPError("secret-token"),
        OpenApiException("secret-token"),
        JSONDecodeError("secret-token", "secret-token", 0),
        UnicodeDecodeError("utf-8", b"secret-token", 0, 1, "secret-token"),
        TimeoutError("secret-token"),
    ],
)
async def test_unconfirmed_provider_outcome_is_uncertain_and_never_retried(
    client: OAuth2Api, operation: Operation, error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """A lost response or server failure cannot prove that cleanup did not happen."""
    with patch.object(client, METHODS[operation], side_effect=error) as revoke:
        result = await _revoke(HydraHumanOAuthCredentialRevoker(client), operation)

    assert result == IdentityRecoveryCleanupState.UNCERTAIN
    assert "secret-token" not in repr(result) + caplog.text
    revoke.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        ApiResponse[None](status_code=200, headers=None, data=None, raw_data=b""),
        ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"unexpected-body"),
    ],
)
async def test_only_an_expected_empty_204_confirms_cleanup(
    client: OAuth2Api, operation: Operation, response: object
) -> None:
    with patch.object(client, METHODS[operation], return_value=response):
        assert await _revoke(HydraHumanOAuthCredentialRevoker(client), operation) == (
            IdentityRecoveryCleanupState.UNCERTAIN
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
@pytest.mark.parametrize("timeout_seconds", [True, 0.0, -1.0, float("nan"), float("inf")])
async def test_invalid_deadline_prevents_the_provider_call(
    client: OAuth2Api, operation: Operation, timeout_seconds: float
) -> None:
    with (
        patch.object(client, METHODS[operation]) as revoke,
        pytest.raises(ValueError, match="finite and positive"),
    ):
        await _revoke(HydraHumanOAuthCredentialRevoker(client), operation, timeout_seconds)
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
async def test_deadline_does_not_wait_for_a_blocked_sdk_thread(
    client: OAuth2Api, operation: Operation
) -> None:
    started, release = Event(), Event()

    def blocked(**_kwargs: object) -> ApiResponse[None]:
        started.set()
        assert release.wait(2.0)
        return ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")

    try:
        with patch.object(client, METHODS[operation], side_effect=blocked) as revoke:
            async with asyncio.timeout(1.0):
                result = await _revoke(HydraHumanOAuthCredentialRevoker(client), operation, 0.05)
            assert started.is_set()
            assert result == IdentityRecoveryCleanupState.UNCERTAIN
            revoke.assert_called_once()
    finally:
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
async def test_cancellation_propagates_without_retrying_the_remote_operation(
    client: OAuth2Api, operation: Operation
) -> None:
    started = asyncio.Event()
    release, finished = Event(), Event()
    loop = asyncio.get_running_loop()

    def blocked(**_kwargs: object) -> ApiResponse[None]:
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(2.0)
            return ApiResponse[None](status_code=204, headers=None, data=None, raw_data=b"")
        finally:
            finished.set()

    try:
        with patch.object(client, METHODS[operation], side_effect=blocked) as revoke:
            task = asyncio.create_task(_revoke(HydraHumanOAuthCredentialRevoker(client), operation))
            async with asyncio.timeout(1.0):
                await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not finished.is_set()
            revoke.assert_called_once()
    finally:
        release.set()
