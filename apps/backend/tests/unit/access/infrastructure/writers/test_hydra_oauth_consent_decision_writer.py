import asyncio
from collections.abc import Iterator
from threading import Event
from traceback import format_exception
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.exceptions import ApiException
from ory_hydra_client.models.o_auth2_redirect_to import OAuth2RedirectTo

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.writers.hydra_oauth_consent_decision_writer import (
    HydraOAuthConsentDecisionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

BINDING = HumanOAuthCredentialBindingDTO(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice")),
    InstallationId(UUID(int=123)),
    HumanCredentialVersion(6),
)

CHALLENGE = OAuthConsentChallenge("private-challenge")
URL = "https://auth.test/base/oauth2/auth?client_id=inframeld-cli&consent_verifier=private-state"


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host="http://admin.test", retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


async def _decide(
    client: OAuth2Api, decision: Literal["allow", "deny"]
) -> OAuthConsentContinuationDTO:
    writer = HydraOAuthConsentDecisionWriter(client, public_url="https://auth.test/base")
    if decision == "deny":
        return await writer.deny(CHALLENGE, timeout_seconds=1.0)
    return await writer.allow(
        CHALLENGE,
        scopes=(HumanOAuthScope.API,),
        audiences=(HumanAPIAudience("https://api.test"),),
        binding=BINDING,
        remember_for_seconds=None,
        timeout_seconds=1.0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("remember", [None, 3600])
async def test_allow_forwards_only_checked_access_and_the_server_duration(
    client: OAuth2Api, remember: int | None
) -> None:
    with patch.object(
        client, "accept_o_auth2_consent_request", return_value=OAuth2RedirectTo(redirect_to=URL)
    ) as accept:
        result = await HydraOAuthConsentDecisionWriter(
            client, public_url="https://auth.test/base/"
        ).allow(
            CHALLENGE,
            scopes=(HumanOAuthScope.API, HumanOAuthScope.OFFLINE_ACCESS),
            audiences=(HumanAPIAudience("https://api.test"),),
            binding=BINDING,
            remember_for_seconds=remember,
            timeout_seconds=1.0,
        )
    assert result.redirect_to == URL
    assert "private-state" not in repr(result)
    assert accept.call_args.kwargs["consent_challenge"] == CHALLENGE.value
    payload = accept.call_args.kwargs["accept_o_auth2_consent_request"]
    assert payload.grant_scope == ["inframeld:api", "offline_access"]
    assert payload.grant_access_token_audience == ["https://api.test"]
    assert payload.remember is (remember is not None)
    assert payload.remember_for == remember
    assert payload.session is not None
    assert payload.session.access_token == {
        "inframeld_installation_id": str(BINDING.installation_id.value),
        "inframeld_credential_version": 6,
    }
    assert payload.session.id_token is None
    assert 0 < accept.call_args.kwargs["_request_timeout"] <= 1.0
    accept.assert_called_once()


@pytest.mark.asyncio
async def test_deny_sends_only_a_fixed_safe_error(client: OAuth2Api) -> None:
    with patch.object(
        client, "reject_o_auth2_consent_request", return_value=OAuth2RedirectTo(redirect_to=URL)
    ) as deny:
        await HydraOAuthConsentDecisionWriter(client, public_url="https://auth.test/base").deny(
            CHALLENGE, timeout_seconds=1.0
        )
    payload = deny.call_args.kwargs["reject_o_auth2_request"]
    assert payload.error == "access_denied"
    assert payload.error_debug is None
    assert payload.error_hint is None
    deny.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/base/oauth2/auth?consent_verifier=x",
        "http://auth.test/base/oauth2/auth?consent_verifier=x",
        "https://user:secret@auth.test/base/oauth2/auth?consent_verifier=x",
        "https://auth.test/other?consent_verifier=x",
        "https://auth.test/base/oauth2/auth?consent_verifier=x#fragment",
        "https://auth.test/base/oauth2/auth",
        "https://auth.test/base/oauth2/auth?consent_verifier=a&consent_verifier=b",
    ],
)
async def test_untrusted_continuation_is_never_returned(client: OAuth2Api, url: str) -> None:
    with (
        patch.object(
            client, "accept_o_auth2_consent_request", return_value=OAuth2RedirectTo(redirect_to=url)
        ),
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await HydraOAuthConsentDecisionWriter(client, public_url="https://auth.test/base").allow(
            CHALLENGE,
            scopes=(HumanOAuthScope.API,),
            audiences=(HumanAPIAudience("https://api.test"),),
            binding=BINDING,
            remember_for_seconds=None,
            timeout_seconds=1.0,
        )
    assert url not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 500])
async def test_an_unconfirmed_decision_is_not_a_confirmed_denial_or_an_automatic_retry(
    client: OAuth2Api, status: int
) -> None:
    with (
        patch.object(
            client,
            "accept_o_auth2_consent_request",
            side_effect=ApiException(status=status, body="private-provider-payload"),
        ) as accept,
        pytest.raises(
            ResourceNotFoundError if status in {400, 404, 410} else DependencyUnavailableError
        ) as caught,
    ):
        await HydraOAuthConsentDecisionWriter(client, public_url="https://auth.test/base").allow(
            CHALLENGE,
            scopes=(HumanOAuthScope.API,),
            audiences=(HumanAPIAudience("https://api.test"),),
            binding=BINDING,
            remember_for_seconds=None,
            timeout_seconds=1.0,
        )
    assert "private-provider-payload" not in str(caught.value)
    accept.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["allow", "deny"])
@pytest.mark.parametrize("interruption", ["deadline", "cancellation"])
async def test_interrupted_decision_does_not_wait_for_or_accept_a_late_sdk_response(
    client: OAuth2Api,
    decision: Literal["allow", "deny"],
    interruption: Literal["deadline", "cancellation"],
) -> None:
    """An uncertain approval stays uncertain even if its SDK call later succeeds."""
    loop = asyncio.get_running_loop()
    started, finished = asyncio.Event(), asyncio.Event()
    release = Event()
    response = OAuth2RedirectTo(redirect_to=URL)

    def blocked(**_kwargs: object) -> OAuth2RedirectTo:
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(5.0), "The test SDK gate was not released."
            return response
        finally:
            loop.call_soon_threadsafe(finished.set)

    expected_error = (
        DependencyUnavailableError if interruption == "deadline" else asyncio.CancelledError
    )
    with (
        patch.object(client, "accept_o_auth2_consent_request", side_effect=blocked) as allow,
        patch.object(client, "reject_o_auth2_consent_request", side_effect=blocked) as deny,
    ):
        selected, opposite = (allow, deny) if decision == "allow" else (deny, allow)
        task = asyncio.create_task(_decide(client, decision))
        try:
            await asyncio.wait_for(started.wait(), timeout=5.0)
            if interruption == "cancellation":
                task.cancel()
            with pytest.raises(expected_error) as caught:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            assert not finished.is_set()
            selected.assert_called_once()
            opposite.assert_not_called()
            timeout: object = selected.call_args.kwargs["_request_timeout"]
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
        selected.assert_called_once()
        opposite.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["allow", "deny"])
async def test_sdk_timeout_does_not_retry_reverse_the_decision_or_disclose_secrets(
    client: OAuth2Api, decision: Literal["allow", "deny"], caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(
            client,
            "accept_o_auth2_consent_request",
            side_effect=TimeoutError("private-provider-timeout"),
        ) as allow,
        patch.object(
            client,
            "reject_o_auth2_consent_request",
            side_effect=TimeoutError("private-provider-timeout"),
        ) as deny,
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await _decide(client, decision)
    diagnostic = "".join(format_exception(caught.value)) + caplog.text
    assert "private-provider-timeout" not in diagnostic
    assert CHALLENGE.value not in diagnostic
    assert "private-state" not in diagnostic
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    selected, opposite = (allow, deny) if decision == "allow" else (deny, allow)
    selected.assert_called_once()
    opposite.assert_not_called()
    timeout: object = selected.call_args.kwargs["_request_timeout"]
    assert isinstance(timeout, float)
    assert 0 < timeout <= 1.0
