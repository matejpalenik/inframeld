"""Check the staged harness without contacting either provider."""

import base64
import hashlib
from dataclasses import replace
from typing import Literal, override
from urllib.parse import parse_qs, urlencode
from uuid import UUID

import httpx2
import pytest
from tests.support.hydra_provider import (
    API_AUDIENCE,
    CLIENT_ID,
    REDIRECT_URI,
    UI_ORIGIN,
    HydraTestProvider,
)
from tests.support.integration_services import HYDRA_PUBLIC_URL
from tests.support.kratos_browser import RegisteredHumanDTO

from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
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
        self, *, fault: Fault = "none", token_status: int = 200, error: str = "invalid_grant"
    ) -> None:
        self.fault = fault
        self.token_status = token_status
        self.error = error
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
                return httpx2.Response(
                    302, headers={"location": f"{UI_ORIGIN}/login?login_challenge=login-secret"}
                )
            if "login_verifier" in params:
                return httpx2.Response(
                    302,
                    headers={"location": f"{UI_ORIGIN}/consent?consent_challenge=consent-secret"},
                )
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
