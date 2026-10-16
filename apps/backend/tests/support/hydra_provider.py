"""Drive real Ory services for backend tests without implementing the account UI.

This helper deliberately approves test login/consent challenges through Hydra's
private API. It is not a production login flow or evidence that the account UI
and CLI have been qualified.
"""

import base64
import hashlib
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx2
from pydantic import BaseModel, ConfigDict, SecretStr

from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer
from tests.support.integration_services import HYDRA_ADMIN_URL, HYDRA_PUBLIC_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import RegisteredHumanDTO, WhoamiResponse

HYDRA_ISSUER = OAuthIssuer(f"{HYDRA_PUBLIC_URL}/")
API_AUDIENCE = HumanAPIAudience("http://inframeld-api.test")
CLIENT_ID = "inframeld-cli"
REDIRECT_URI = "http://127.0.0.1:49152/oauth/callback"
UI_ORIGIN = "http://hydra-test-ui.invalid"


class _RedirectResponse(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    redirect_to: SecretStr


class _ClientReference(BaseModel):
    client_id: str


class _ConsentRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    client: _ClientReference
    subject: str
    requested_scope: list[str]
    requested_access_token_audience: list[str]


class _TokenResponse(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    access_token: SecretStr
    refresh_token: SecretStr
    token_type: str


@dataclass(frozen=True, slots=True)
class IssuedHydraTokensDTO:
    """Keep issued credentials out of incidental test representations."""

    access_token: HumanAccessTokenCredential = field(repr=False)
    refresh_token: SecretStr = field(repr=False)


def _require_status(response: httpx2.Response, expected: int) -> None:
    # OAuth/admin response bodies can contain credentials. Never print them.
    assert response.status_code == expected, (
        f"Ory test request returned {response.status_code}; expected {expected}."
    )


def _single_query_value(url: str, name: str) -> str:
    values = parse_qs(urlsplit(url).query).get(name, [])
    assert len(values) == 1, f"Expected one {name} value in the test redirect."
    return values[0]


def _challenge(response: httpx2.Response, phase: str) -> str:
    assert response.status_code in {302, 303}
    location = response.headers["location"]
    parsed = urlsplit(location)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{UI_ORIGIN}/{phase}"
    return _single_query_value(location, f"{phase}_challenge")


def _hydra_redirect(response: httpx2.Response) -> str:
    _require_status(response, 200)
    location = _RedirectResponse.model_validate_json(response.text).redirect_to.get_secret_value()
    parsed = urlsplit(location)
    assert f"{parsed.scheme}://{parsed.netloc}" == HYDRA_PUBLIC_URL
    assert parsed.path == "/oauth2/auth"
    return location


class HydraTestProvider:
    """Exercise real provider HTTP APIs on the private test network."""

    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client

    async def issue_tokens(
        self,
        human: RegisteredHumanDTO,
        *,
        include_audience: bool = True,
    ) -> IssuedHydraTokensDTO:
        """Use a verified Kratos subject in an S256 authorization-code test exchange.

        These explicit protocol requests exercise the server in a test. The
        production CLI still needs its maintained OAuth/OIDC library, callback
        listener, ID-token validation and account UI integration.
        """
        whoami = await self._client.get(
            f"{KRATOS_PUBLIC_URL}/sessions/whoami",
            headers={"Cookie": f"ory_kratos_session={human.credential.value}"},
        )
        _require_status(whoami, 200)
        subject = IdentitySubject(str(WhoamiResponse.model_validate_json(whoami.text).identity.id))
        assert subject == human.subject

        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            # This increment exercises OAuth access/refresh tokens, not an ID token.
            "scope": "inframeld:api offline_access",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if include_audience:
            params["audience"] = API_AUDIENCE.value

        started = await self._client.get(f"{HYDRA_PUBLIC_URL}/oauth2/auth", params=params)
        login_challenge = _challenge(started, "login")
        accepted_login = await self._client.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/login/accept",
            params={"login_challenge": login_challenge},
            json={"subject": subject.value, "remember": False},
        )
        consent_redirect = await self._client.get(_hydra_redirect(accepted_login))
        consent_challenge = _challenge(consent_redirect, "consent")

        consent_response = await self._client.get(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent",
            params={"consent_challenge": consent_challenge},
        )
        _require_status(consent_response, 200)
        consent = _ConsentRequest.model_validate_json(consent_response.text)
        assert consent.client.client_id == CLIENT_ID
        assert consent.subject == subject.value
        assert set(consent.requested_scope) == {"inframeld:api", "offline_access"}
        expected_audience = [API_AUDIENCE.value] if include_audience else []
        assert consent.requested_access_token_audience == expected_audience

        accepted_consent = await self._client.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent/accept",
            params={"consent_challenge": consent_challenge},
            json={
                "grant_scope": consent.requested_scope,
                "grant_access_token_audience": consent.requested_access_token_audience,
                "remember": False,
            },
        )
        callback_redirect = await self._client.get(_hydra_redirect(accepted_consent))
        assert callback_redirect.status_code in {302, 303}
        callback = callback_redirect.headers["location"]
        parsed_callback = urlsplit(callback)
        assert (
            f"{parsed_callback.scheme}://{parsed_callback.netloc}{parsed_callback.path}"
            == REDIRECT_URI
        )
        assert secrets.compare_digest(_single_query_value(callback, "state"), state)
        assert "error" not in parse_qs(parsed_callback.query)
        code = _single_query_value(callback, "code")

        # Inspect the callback; do not send a request to its loopback address.
        exchanged = await self._client.post(
            f"{HYDRA_PUBLIC_URL}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
            },
        )
        _require_status(exchanged, 200)
        tokens = _TokenResponse.model_validate_json(exchanged.text)
        assert tokens.token_type.casefold() == "bearer"
        return IssuedHydraTokensDTO(
            access_token=HumanAccessTokenCredential(tokens.access_token.get_secret_value()),
            refresh_token=tokens.refresh_token,
        )

    async def revoke_access_token(self, credential: HumanAccessTokenCredential) -> None:
        response = await self._client.post(
            f"{HYDRA_PUBLIC_URL}/oauth2/revoke",
            data={
                "client_id": CLIENT_ID,
                "token": credential.value,
                "token_type_hint": "access_token",
            },
        )
        _require_status(response, 200)


@asynccontextmanager
async def hydra_test_provider() -> AsyncGenerator[HydraTestProvider]:
    """Own one test client registration; remove it even after a scenario fails.

    This runs only against the dedicated Hydra test database. Tests using this
    fixed first-party client must run sequentially.
    """
    async with httpx2.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False) as client:
        client_url = f"{HYDRA_ADMIN_URL}/admin/clients/{CLIENT_ID}"
        removed = await client.delete(client_url)
        assert removed.status_code in {204, 404}
        created = await client.post(
            f"{HYDRA_ADMIN_URL}/admin/clients",
            json={
                "client_id": CLIENT_ID,
                "client_name": "Inframeld CLI integration test",
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "redirect_uris": [REDIRECT_URI],
                "scope": "openid offline_access inframeld:api",
                "audience": [API_AUDIENCE.value],
                "subject_type": "public",
                "access_token_strategy": "opaque",
                "skip_consent": False,
            },
        )
        _require_status(created, 201)
        try:
            yield HydraTestProvider(client)
        finally:
            _require_status(await client.delete(client_url), 204)
