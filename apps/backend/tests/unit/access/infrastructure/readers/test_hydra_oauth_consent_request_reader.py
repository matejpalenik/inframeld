import asyncio
from collections.abc import Iterator
from threading import Event
from traceback import format_exception
from typing import Literal
from unittest.mock import patch

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.exceptions import ApiException
from ory_hydra_client.models.o_auth2_client import OAuth2Client
from ory_hydra_client.models.o_auth2_consent_request import OAuth2ConsentRequest
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.infrastructure.readers.hydra_oauth_consent_request_reader import (
    HydraOAuthConsentRequestReader,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)

CHALLENGE = OAuthConsentChallenge("secret-consent-state")


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host="http://hydra-admin.test:4445", retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


def _request() -> OAuth2ConsentRequest:
    return OAuth2ConsentRequest(
        challenge=CHALLENGE.value,
        client=OAuth2Client(client_id="inframeld-cli", skip_consent=False),
        subject="alice",
        requested_scope=["openid", "inframeld:api", "offline_access"],
        requested_access_token_audience=["https://api.test"],
        skip=False,
    )


@pytest.mark.asyncio
async def test_request_is_converted_without_retaining_the_sensitive_provider_envelope(
    client: OAuth2Api,
) -> None:
    with patch.object(client, "get_o_auth2_consent_request", return_value=_request()) as read:
        result = await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)
    assert result.subject.value == "alice"
    assert result.client_id.value == "inframeld-cli"
    assert result.scopes == (
        HumanOAuthScope.OPENID,
        HumanOAuthScope.API,
        HumanOAuthScope.OFFLINE_ACCESS,
    )
    assert tuple(a.value for a in result.audiences) == ("https://api.test",)
    assert not result.skip
    assert CHALLENGE.value not in repr(result)
    assert read.call_args.kwargs["consent_challenge"] == CHALLENGE.value
    assert 0 < read.call_args.kwargs["_request_timeout"] <= 1.0
    read.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["subject", "client", "requested_scope", "requested_access_token_audience", "skip"]
)
async def test_missing_provider_fields_fail_closed(client: OAuth2Api, field: str) -> None:
    response = _request()
    setattr(response, field, None)
    with (
        patch.object(client, "get_o_auth2_consent_request", return_value=response),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_unknown_scope_is_denied_rather_than_forwarded(client: OAuth2Api) -> None:
    response = _request()
    response.requested_scope = ["inframeld:api", "admin"]
    with (
        patch.object(client, "get_o_auth2_consent_request", return_value=response),
        pytest.raises(AccessDeniedError),
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_client_wide_skip_cannot_replace_alices_approval(client: OAuth2Api) -> None:
    response = _request()
    assert response.client is not None
    response.client.skip_consent = True
    response.skip = True
    with (
        patch.object(client, "get_o_auth2_consent_request", return_value=response),
        pytest.raises(AccessDeniedError),
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_provider_must_return_the_requested_challenge(client: OAuth2Api) -> None:
    response = _request()
    response.challenge = "another-secret"
    with (
        patch.object(client, "get_o_auth2_consent_request", return_value=response),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,error_type",
    [
        (404, ResourceNotFoundError),
        (410, ResourceNotFoundError),
        (400, ResourceNotFoundError),
        (401, DependencyUnavailableError),
        (403, DependencyUnavailableError),
        (500, DependencyUnavailableError),
    ],
)
async def test_provider_errors_are_safe_and_never_retried(
    client: OAuth2Api, status: int, error_type: type[Exception]
) -> None:
    with (
        patch.object(
            client,
            "get_o_auth2_consent_request",
            side_effect=ApiException(status=status, body="secret-provider-payload"),
        ) as read,
        pytest.raises(error_type) as caught,
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)
    assert "secret-provider-payload" not in str(caught.value)
    assert caught.value.__suppress_context__
    read.assert_called_once()


@pytest.mark.asyncio
async def test_network_failure_is_unavailable(client: OAuth2Api) -> None:
    with (
        patch.object(client, "get_o_auth2_consent_request", side_effect=HTTPError("private")),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["deadline", "cancellation"])
async def test_interrupted_read_does_not_wait_for_or_accept_a_late_sdk_response(
    client: OAuth2Api, interruption: Literal["deadline", "cancellation"]
) -> None:
    """Stopping the caller does not stop the SDK thread or make its late response usable."""
    loop = asyncio.get_running_loop()
    started, finished = asyncio.Event(), asyncio.Event()
    release = Event()
    response = _request()

    def blocked(**_kwargs: object) -> OAuth2ConsentRequest:
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(5.0), "The test SDK gate was not released."
            return response
        finally:
            loop.call_soon_threadsafe(finished.set)

    expected_error = (
        DependencyUnavailableError if interruption == "deadline" else asyncio.CancelledError
    )
    with patch.object(client, "get_o_auth2_consent_request", side_effect=blocked) as read:
        task = asyncio.create_task(
            HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=5.0)
            if interruption == "cancellation":
                task.cancel()
            with pytest.raises(expected_error) as caught:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            assert not finished.is_set()
            read.assert_called_once()
            timeout: object = read.call_args.kwargs["_request_timeout"]
            assert isinstance(timeout, float)
            assert 0 < timeout <= 1.0
        finally:
            release.set()
            if not task.done():
                task.cancel()
            async with asyncio.timeout(5.0):
                await asyncio.gather(task, return_exceptions=True)
                await finished.wait()

        assert finished.is_set()
        if interruption == "cancellation":
            assert task.cancelled()
        else:
            assert task.exception() is caught.value
        read.assert_called_once()


@pytest.mark.asyncio
async def test_sdk_timeout_is_unavailable_without_retry_or_secret_disclosure(
    client: OAuth2Api, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(
            client,
            "get_o_auth2_consent_request",
            side_effect=TimeoutError("private-provider-timeout"),
        ) as read,
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await HydraOAuthConsentRequestReader(client).read(CHALLENGE, timeout_seconds=1.0)
    diagnostic = "".join(format_exception(caught.value)) + caplog.text
    assert "private-provider-timeout" not in diagnostic
    assert CHALLENGE.value not in diagnostic
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    read.assert_called_once()
    timeout: object = read.call_args.kwargs["_request_timeout"]
    assert isinstance(timeout, float)
    assert 0 < timeout <= 1.0
