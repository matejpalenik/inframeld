"""A provider decision may finish remotely after the caller stops waiting."""

import asyncio
from collections.abc import Iterator
from threading import Event
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
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
from inframeld_backend.access.infrastructure.readers.hydra_oauth_consent_request_reader import (
    HydraOAuthConsentRequestReader,
)
from inframeld_backend.access.infrastructure.writers.hydra_oauth_consent_decision_writer import (
    HydraOAuthConsentDecisionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

BINDING = HumanOAuthCredentialBindingDTO(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice")),
    InstallationId(UUID(int=123)),
    HumanCredentialVersion(6),
)

type Operation = Literal["read", "allow", "deny"]
METHODS: dict[Operation, str] = {
    "read": "get_o_auth2_consent_request",
    "allow": "accept_o_auth2_consent_request",
    "deny": "reject_o_auth2_consent_request",
}


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host="http://admin.test", retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


async def _call(client: OAuth2Api, operation: Operation, seconds: float) -> None:
    challenge = OAuthConsentChallenge("private-challenge")
    if operation == "read":
        await HydraOAuthConsentRequestReader(client).read(challenge, timeout_seconds=seconds)
    else:
        writer = HydraOAuthConsentDecisionWriter(client, public_url="https://auth.test")
        if operation == "deny":
            await writer.deny(challenge, timeout_seconds=seconds)
        else:
            await writer.allow(
                challenge,
                scopes=(HumanOAuthScope.API,),
                audiences=(HumanAPIAudience("https://api.test"),),
                binding=BINDING,
                remember_for_seconds=None,
                timeout_seconds=seconds,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "allow", "deny"])
@pytest.mark.parametrize("seconds", [True, 0, -1, float("inf"), float("nan")])
async def test_invalid_timeout_never_contacts_hydra(
    client: OAuth2Api, operation: Operation, seconds: float
) -> None:
    with patch.object(client, METHODS[operation]) as call, pytest.raises(ValueError):
        await _call(client, operation, seconds)
    call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "allow", "deny"])
async def test_deadline_stops_waiting_without_retrying_the_sdk_thread(
    client: OAuth2Api, operation: Operation
) -> None:
    started, release = Event(), Event()

    def blocked(**_kwargs: object) -> None:
        started.set()
        assert release.wait(2.0)

    try:
        with patch.object(client, METHODS[operation], side_effect=blocked) as call:
            async with asyncio.timeout(1.0):
                with pytest.raises(DependencyUnavailableError):
                    await _call(client, operation, 0.02)
            assert started.is_set()
            call.assert_called_once()
    finally:
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "allow", "deny"])
async def test_cancellation_propagates_while_the_remote_call_may_still_finish(
    client: OAuth2Api, operation: Operation
) -> None:
    started = asyncio.Event()
    release = Event()
    loop = asyncio.get_running_loop()

    def blocked(**_kwargs: object) -> None:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(2.0)

    try:
        with patch.object(client, METHODS[operation], side_effect=blocked) as call:
            task = asyncio.create_task(_call(client, operation, 1.0))
            async with asyncio.timeout(1.0):
                await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            call.assert_called_once()
    finally:
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["allow", "deny"])
async def test_lost_acknowledgement_is_unavailable_and_does_not_replay_the_decision(
    client: OAuth2Api, operation: Operation
) -> None:
    with (
        patch.object(
            client, METHODS[operation], side_effect=HTTPError("private-provider-data")
        ) as call,
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await _call(client, operation, 1.0)
    assert "private-provider-data" not in str(caught.value)
    call.assert_called_once()
