"""Check the staged harness without contacting either provider."""

import asyncio
import base64
import hashlib
from dataclasses import replace
from typing import Literal, override
from urllib.parse import parse_qs, urlencode
from uuid import UUID

import httpx2
import pytest
from pydantic import SecretStr
from tests.support.hydra_provider import (
    API_AUDIENCE,
    CLIENT_ID,
    REDIRECT_URI,
    UI_ORIGIN,
    HydraAuthorizationRejectedError,
    HydraTestEndpointsDTO,
    HydraTestProvider,
    IssuedHydraTokensDTO,
    PKCEChallenge,
)
from tests.support.hydra_token_request_gate import HydraTokenRequestGate
from tests.support.integration_services import HYDRA_PUBLIC_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import RegisteredHumanDTO

from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject

SUBJECT = IdentitySubject("1d786a3b-b130-43ec-8cec-52afef9c7772")
SESSION = UUID("2d786a3b-b130-43ec-8cec-52afef9c7772")
HUMAN = RegisteredHumanDTO(
    SUBJECT, "alice@example.test", "password-secret", BrowserSessionCredential("cookie-secret")
)
type Fault = Literal[
    "none",
    "identity",
    "callback_destination",
    "callback_state",
    "duplicate_code",
    "oauth_error",
    "client",
    "subject",
    "session",
    "scopes",
    "audience",
    "admin_redirect",
]


class MockHydraTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        *,
        fault: Fault = "none",
        token_status: int = 200,
        error: str = "invalid_grant",
        authorization_error: str | None = None,
        error_stage: Literal["start", "login", "consent"] = "consent",
    ) -> None:
        self.fault = fault
        self.token_status = token_status
        self.error = error
        self.authorization_error = authorization_error
        self.error_stage = error_stage
        self.requests: list[httpx2.Request] = []
        self.authorization: dict[str, str] = {}

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/sessions/whoami":
            return httpx2.Response(
                200,
                json={
                    "identity": {"id": str(SESSION) if self.fault == "identity" else SUBJECT.value}
                },
            )
        if path == "/oauth2/auth":
            params = dict(request.url.params)
            if "response_type" in params:
                self.authorization = params
                if self.authorization_error is not None and self.error_stage == "start":
                    return self._error_callback()
                return httpx2.Response(
                    302,
                    headers={
                        "location": f"{KRATOS_PUBLIC_URL}/self-service/login/browser?login_challenge=login-secret"
                    },
                )
            if "login_verifier" in params:
                if self.authorization_error is not None and self.error_stage == "login":
                    return self._error_callback()
                return httpx2.Response(
                    302,
                    headers={"location": f"{UI_ORIGIN}/consent?consent_challenge=consent-secret"},
                )
            if self.authorization_error is not None:
                return self._error_callback()
            callback_params = {
                "state": self.authorization["state"],
                "code": "authorization-code-secret",
            }
            destination = REDIRECT_URI
            if self.fault == "callback_destination":
                destination = "http://unexpected.test/callback"
            if self.fault == "callback_state":
                callback_params["state"] = "wrong-state-secret"
            if self.fault == "oauth_error":
                callback_params = {"state": self.authorization["state"], "error": "access_denied"}
            callback = f"{destination}?{urlencode(callback_params)}"
            if self.fault == "duplicate_code":
                callback += "&code=second-code-secret"
            return httpx2.Response(302, headers={"location": callback})
        if path == "/admin/oauth2/auth/requests/login":
            return httpx2.Response(200, json={"session_id": str(SESSION), "skip": False})
        if path.endswith("/login/accept") or path.endswith("/consent/accept"):
            phase = "login" if path.endswith("/login/accept") else "consent"
            origin = (
                "http://unexpected.test" if self.fault == "admin_redirect" else HYDRA_PUBLIC_URL
            )
            return httpx2.Response(
                200, json={"redirect_to": f"{origin}/oauth2/auth?{phase}_verifier=private-verifier"}
            )
        if path == "/admin/oauth2/auth/requests/consent":
            return httpx2.Response(
                200,
                json={
                    "client": {
                        "client_id": "other-client" if self.fault == "client" else CLIENT_ID
                    },
                    "subject": "other-subject" if self.fault == "subject" else SUBJECT.value,
                    "requested_scope": []
                    if self.fault == "scopes"
                    else ["inframeld:api", "offline_access"],
                    "requested_access_token_audience": []
                    if self.fault == "audience"
                    else [API_AUDIENCE.value],
                    "login_session_id": str(UUID(int=0))
                    if self.fault == "session"
                    else str(SESSION),
                    "skip": False,
                },
            )
        if path == "/oauth2/token":
            if self.token_status != 200:
                return httpx2.Response(
                    self.token_status,
                    json={"error": self.error, "error_description": "provider-detail-secret"},
                )
            return httpx2.Response(
                200,
                json={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "token_type": "Bearer",
                },
            )
        raise AssertionError("Unexpected test request.")

    def _error_callback(self) -> httpx2.Response:
        params = {
            "state": "wrong-state-secret"
            if self.fault == "callback_state"
            else self.authorization["state"],
            "error": self.authorization_error,
            "error_description": "provider-detail-secret",
        }
        return httpx2.Response(302, headers={"location": f"{REDIRECT_URI}?{urlencode(params)}"})


@pytest.mark.asyncio
async def test_stages_stop_before_approval_and_exchange_with_the_original_pkce_values() -> None:
    """A test can let cleanup finish between steps without issuing tokens accidentally."""
    transport = MockHydraTransport()
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        pending = await provider.begin_login(HUMAN)
        assert [request.url.path for request in transport.requests] == [
            "/sessions/whoami",
            "/oauth2/auth",
            "/admin/oauth2/auth/requests/login",
        ]
        assert pending.subject == SUBJECT
        assert pending.login_session_id == SESSION
        assert transport.authorization["code_challenge_method"] == "S256"
        digest = hashlib.sha256(pending.verifier.get_secret_value().encode("ascii")).digest()
        assert transport.authorization["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(
            b"="
        ).decode("ascii")

        code = await provider.approve_login_and_consent(pending)
        assert not any(request.url.path == "/oauth2/token" for request in transport.requests)
        tokens = await provider.exchange_authorization_code(code)
        assert tokens is not None
        assert tokens.access_token.value == "access-secret"
        assert tokens.refresh_token.get_secret_value() == "refresh-secret"
        exchange = transport.requests[-1]
        assert parse_qs(exchange.content.decode()) == {
            "client_id": [CLIENT_ID],
            "redirect_uri": [REDIRECT_URI],
            "grant_type": ["authorization_code"],
            "code": [code.code.get_secret_value()],
            "code_verifier": [pending.verifier.get_secret_value()],
        }
        representations = repr(pending) + repr(code) + repr(tokens)
        for secret in (
            "login-secret",
            "authorization-code-secret",
            "access-secret",
            "refresh-secret",
            pending.state.get_secret_value(),
            pending.verifier.get_secret_value(),
        ):
            assert secret not in representations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "callback_destination",
        "callback_state",
        "duplicate_code",
        "oauth_error",
        "client",
        "subject",
        "session",
        "scopes",
        "audience",
        "admin_redirect",
    ],
)
async def test_invalid_provider_binding_or_callback_never_reaches_token_exchange(
    fault: Fault,
) -> None:
    transport = MockHydraTransport(fault=fault)
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        pending = await provider.begin_login(HUMAN)
        with pytest.raises(AssertionError) as failure:
            await provider.approve_login_and_consent(pending)
        assert not any(request.url.path == "/oauth2/token" for request in transport.requests)
        for secret in (
            "login-secret",
            "private-verifier",
            "authorization-code-secret",
            "wrong-state-secret",
            "provider-detail-secret",
        ):
            assert secret not in str(failure.value)


@pytest.mark.asyncio
async def test_wrong_kratos_identity_is_rejected_before_starting_authorization() -> None:
    transport = MockHydraTransport(fault="identity")
    async with httpx2.AsyncClient(transport=transport) as client:
        with pytest.raises(AssertionError):
            await HydraTestProvider(client).begin_login(HUMAN)
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["approval", "exchange"])
async def test_a_staged_record_for_another_client_is_rejected_before_io(stage: str) -> None:
    transport = MockHydraTransport()
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        pending = await provider.begin_login(HUMAN)
        if stage == "approval":
            before = len(transport.requests)
            with pytest.raises(AssertionError):
                await provider.approve_login_and_consent(replace(pending, client_id="other-client"))
        else:
            code = await provider.approve_login_and_consent(pending)
            before = len(transport.requests)
            with pytest.raises(AssertionError):
                await provider.exchange_authorization_code(replace(code, client_id="other-client"))
        assert len(transport.requests) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error"), [(400, "invalid_grant"), (400, "invalid_client"), (500, "server_error")]
)
async def test_only_explicit_invalid_grant_means_a_denied_code_without_retries(
    status: int, error: str
) -> None:
    transport = MockHydraTransport(token_status=status, error=error)
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        code = await provider.approve_login_and_consent(await provider.begin_login(HUMAN))
        if status == 400 and error == "invalid_grant":
            assert await provider.exchange_authorization_code(code) is None
        else:
            with pytest.raises(AssertionError) as failure:
                await provider.exchange_authorization_code(code)
            assert "provider-detail-secret" not in str(failure.value)
        assert sum(request.url.path == "/oauth2/token" for request in transport.requests) == 1


@pytest.mark.asyncio
async def test_provider_setup_failure_restores_http_client_logging() -> None:
    import logging

    from tests.support.hydra_provider import hydra_test_provider

    logger = logging.getLogger("httpx2")
    previous = logger.level
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(500))
    try:
        with pytest.raises(AssertionError):
            async with hydra_test_provider(transport=transport):
                raise AssertionError("Setup unexpectedly succeeded.")
        assert logger.level == previous
    finally:
        logger.setLevel(previous)


@pytest.mark.asyncio
async def test_only_explicit_binding_is_written_to_test_consent_metadata() -> None:
    import json

    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )
    from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
        VerifiedHumanIdentityDTO,
    )
    from inframeld_backend.access.domain.value_objects.human_credential_version import (
        HumanCredentialVersion,
    )
    from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
    from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

    transport = MockHydraTransport()
    binding = HumanOAuthCredentialBindingDTO(
        VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), SUBJECT),
        InstallationId(UUID(int=123)),
        HumanCredentialVersion(6),
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        await provider.approve_login_and_consent(
            await provider.begin_login(HUMAN), credential_binding=binding
        )
    accepted = next(
        request for request in transport.requests if request.url.path.endswith("/consent/accept")
    )
    assert json.loads(accepted.content)["session"]["access_token"] == {
        "inframeld_installation_id": str(binding.installation_id.value),
        "inframeld_credential_version": 6,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("pkce", ["missing", "plain", "missing_method"])
async def test_negative_pkce_parameters_reach_hydra(pkce: PKCEChallenge) -> None:
    """The harness sends the invalid proof instead of rejecting it locally."""
    transport = MockHydraTransport()
    async with httpx2.AsyncClient(transport=transport) as client:
        pending = await HydraTestProvider(client).begin_login(HUMAN, pkce=pkce)
    params = transport.authorization
    if pkce == "missing":
        assert "code_challenge" not in params
        assert "code_challenge_method" not in params
    else:
        assert params["code_challenge"] == pending.verifier.get_secret_value()
        if pkce == "plain":
            assert params["code_challenge_method"] == "plain"
        else:
            assert "code_challenge_method" not in params


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["start", "login", "consent"])
async def test_expected_authorization_rejection_keeps_only_the_error_category(
    stage: Literal["start", "login", "consent"],
) -> None:
    transport = MockHydraTransport(authorization_error="invalid_request", error_stage=stage)
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        with pytest.raises(HydraAuthorizationRejectedError) as failure:
            await provider.approve_login_and_consent(await provider.begin_login(HUMAN))
    assert failure.value.error == "invalid_request"
    assert "provider-detail-secret" not in str(failure.value)
    assert not any(request.url.path == "/oauth2/token" for request in transport.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["none", "callback_state"])
async def test_unknown_or_unbound_oauth_error_is_not_an_expected_rejection(fault: Fault) -> None:
    transport = MockHydraTransport(
        fault=fault,
        authorization_error="provider-detail-secret" if fault == "none" else "invalid_request",
    )
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        with pytest.raises(AssertionError) as failure:
            await provider.approve_login_and_consent(await provider.begin_login(HUMAN))
    assert not isinstance(failure.value, HydraAuthorizationRejectedError)
    assert "provider-detail-secret" not in str(failure.value)
    assert "wrong-state-secret" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("omit", [False, True])
async def test_exchange_sends_the_selected_verifier_once_or_omits_it(omit: bool) -> None:
    transport = MockHydraTransport(token_status=400)
    async with httpx2.AsyncClient(transport=transport) as client:
        provider = HydraTestProvider(client)
        code = await provider.approve_login_and_consent(await provider.begin_login(HUMAN))
        code = replace(code, verifier=SecretStr("V" * 64))
        assert await provider.exchange_authorization_code(code, omit_verifier=omit) is None
    requests = [request for request in transport.requests if request.url.path == "/oauth2/token"]
    assert len(requests) == 1
    params = parse_qs(requests[0].content.decode())
    assert params.get("code_verifier") == (None if omit else ["V" * 64])


@pytest.mark.asyncio
async def test_selected_revocation_sends_only_the_refresh_token_and_public_client() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        await HydraTestProvider(client).revoke_refresh_token(SecretStr("selected-refresh-secret"))
    assert len(requests) == 1
    assert str(requests[0].url) == f"{HYDRA_PUBLIC_URL}/oauth2/revoke"
    assert parse_qs(requests[0].content.decode()) == {
        "client_id": [CLIENT_ID],
        "token": ["selected-refresh-secret"],
        "token_type_hint": ["refresh_token"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["rejection", "transport"])
async def test_selected_revocation_failure_is_not_retried_or_reported_as_success(
    failure_kind: str,
) -> None:
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if failure_kind == "transport":
            raise httpx2.ReadError("Test response was lost.", request=request)
        return httpx2.Response(500, text="provider-detail-secret")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        expected_error = httpx2.ReadError if failure_kind == "transport" else AssertionError
        with pytest.raises(expected_error) as failure:
            await HydraTestProvider(client).revoke_refresh_token(SecretStr("refresh-secret"))
    assert calls == 1
    assert "provider-detail-secret" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed", [None, "active", "iss", "sub", "client_id", "aud", "installation", "version"]
)
async def test_binding_observation_checks_every_allowlisted_identity_field(
    changed: str | None,
) -> None:
    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )
    from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
        VerifiedHumanIdentityDTO,
    )
    from inframeld_backend.access.application.value_objects.human_access_token_credential import (
        HumanAccessTokenCredential,
    )
    from inframeld_backend.access.domain.value_objects.human_credential_version import (
        HumanCredentialVersion,
    )
    from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
    from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

    binding = HumanOAuthCredentialBindingDTO(
        VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), SUBJECT),
        InstallationId(UUID(int=123)),
        HumanCredentialVersion(6),
    )
    metadata: dict[str, object] = {
        "inframeld_installation_id": str(binding.installation_id.value),
        "inframeld_credential_version": 6,
    }
    payload: dict[str, object] = {
        "active": True,
        "iss": f"{HYDRA_PUBLIC_URL}/",
        "sub": SUBJECT.value,
        "client_id": CLIENT_ID,
        "aud": [API_AUDIENCE.value],
        "ext": metadata,
    }
    if changed == "active":
        payload[changed] = False
    elif changed in {"iss", "sub", "client_id"}:
        payload[changed] = "another-value"
    elif changed == "aud":
        payload[changed] = ["another-audience"]
    elif changed == "installation":
        metadata["inframeld_installation_id"] = str(UUID(int=456))
    elif changed == "version":
        metadata["inframeld_credential_version"] = 7
    calls = 0

    def respond(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json=payload)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        provider = HydraTestProvider(client)
        if changed is None:
            await provider.assert_token_binding(
                HumanAccessTokenCredential("token-secret"), binding=binding
            )
        else:
            with pytest.raises(AssertionError):
                await provider.assert_token_binding(
                    HumanAccessTokenCredential("token-secret"), binding=binding
                )
    assert calls == 1


@pytest.mark.asyncio
async def test_losing_a_refresh_response_propagates_cancellation_without_retrying() -> None:
    """A successful server response is not a replacement pair the caller received."""
    transport = MockHydraTransport()
    gate = HydraTokenRequestGate(transport)
    original = IssuedHydraTokensDTO(
        HumanAccessTokenCredential("old-access-secret"), SecretStr("old-refresh-secret")
    )
    async with asyncio.timeout(5.0), httpx2.AsyncClient(transport=gate) as client:
        gate.arm("after_response")
        refresh = asyncio.create_task(HydraTestProvider(client).refresh_tokens(original))
        try:
            await gate.wait_until_paused()
            assert gate.response_status == 200
            assert not refresh.done()
            refresh.cancel()
            with pytest.raises(asyncio.CancelledError):
                await refresh
        finally:
            if not refresh.done():
                refresh.cancel()
            await asyncio.gather(refresh, return_exceptions=True)
    assert len(transport.requests) == 1
    assert parse_qs(transport.requests[0].content.decode()) == {
        "client_id": [CLIENT_ID],
        "grant_type": ["refresh_token"],
        "refresh_token": ["old-refresh-secret"],
    }


@pytest.mark.asyncio
async def test_ambiguous_refresh_transport_failure_is_not_retried() -> None:
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        raise httpx2.ReadTimeout("Test refresh acknowledgement was lost.", request=request)

    original = IssuedHydraTokensDTO(
        HumanAccessTokenCredential("old-access-secret"), SecretStr("old-refresh-secret")
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as client:
        with pytest.raises(httpx2.ReadTimeout):
            await HydraTestProvider(client).refresh_tokens(original)
    assert calls == 1


@pytest.mark.asyncio
async def test_explicit_test_endpoints_and_loopback_port_reach_the_selected_provider() -> None:
    transport = MockHydraTransport()
    endpoints = HydraTestEndpointsDTO("http://hydra-lifetimes:4444", "http://hydra-lifetimes:4445")
    async with httpx2.AsyncClient(transport=transport) as client:
        await HydraTestProvider(
            client, endpoints=endpoints, redirect_uri="http://127.0.0.1:52731/oauth/callback"
        ).begin_login(HUMAN)
    assert str(transport.requests[1].url).startswith(f"{endpoints.public_url}/oauth2/auth?")
    assert str(transport.requests[2].url).startswith(f"{endpoints.admin_url}/admin/")
    assert transport.authorization["redirect_uri"] == "http://127.0.0.1:52731/oauth/callback"
