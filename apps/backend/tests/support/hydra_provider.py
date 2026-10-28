"""Drive real Ory services for backend tests without implementing the account UI.

This helper deliberately approves test login/consent challenges through Hydra's
private API. It is not a production login flow or evidence that the account UI
and CLI have been qualified.
"""

import base64
import hashlib
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx2
from pydantic import BaseModel, ConfigDict, SecretStr, StrictInt

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer
from tests.support.integration_services import HYDRA_ADMIN_URL, HYDRA_PUBLIC_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import (
    BrowserFlow,
    RegisteredHumanDTO,
    WhoamiResponse,
    read_browser_csrf_token,
)

HYDRA_ISSUER = OAuthIssuer(f"{HYDRA_PUBLIC_URL}/")
API_AUDIENCE = HumanAPIAudience("http://inframeld-api.test")
CLIENT_ID = "inframeld-cli"
REDIRECT_URI = "http://127.0.0.1:49152/oauth/callback"
UI_ORIGIN = "http://hydra-test-ui.invalid"

type PKCEChallenge = Literal["S256", "missing", "plain", "missing_method"]


@dataclass(frozen=True, slots=True)
class HydraTestEndpointsDTO:
    public_url: str = HYDRA_PUBLIC_URL
    admin_url: str = HYDRA_ADMIN_URL


DEFAULT_HYDRA_ENDPOINTS = HydraTestEndpointsDTO()


class HydraAuthorizationRejectedError(AssertionError):
    """Expose only the OAuth error category from a validated test callback."""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__(f"Hydra rejected OAuth authorization with error category '{error}'.")


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
    login_session_id: UUID
    skip: bool


class _LoginRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    session_id: UUID
    skip: bool
    subject: str | None = None


class _IntrospectionResponse(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    active: bool


class _CredentialMetadata(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    inframeld_installation_id: UUID
    inframeld_credential_version: StrictInt


class _BoundIntrospectionResponse(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    active: bool
    iss: str
    sub: str
    client_id: str
    aud: list[str]
    ext: _CredentialMetadata


class _OAuthError(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    error: str


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
    consent_skipped: bool = False


@dataclass(frozen=True, slots=True)
class PendingHydraLoginDTO:
    """Retain a verified test subject while login approval is deliberately paused."""

    subject: IdentitySubject
    client_id: str
    login_session_id: UUID
    include_audience: bool
    challenge: SecretStr = field(repr=False)
    verifier: SecretStr = field(repr=False)
    state: SecretStr = field(repr=False)


@dataclass(frozen=True, slots=True)
class HydraAuthorizationCodeDTO:
    """Hold an unexchanged test code and its matching PKCE verifier privately."""

    client_id: str
    code: SecretStr = field(repr=False)
    verifier: SecretStr = field(repr=False)
    consent_skipped: bool = False


@dataclass(frozen=True, slots=True)
class PendingHydraConsentDTO:
    """Keep an unfinished native login private until the consent API decides it."""

    client_id: str
    challenge: SecretStr = field(repr=False)
    verifier: SecretStr = field(repr=False)
    state: SecretStr = field(repr=False)
    consent_skipped: bool = False


@dataclass(frozen=True, slots=True)
class _ConsentFlow:
    consent: _ConsentRequest
    challenge: SecretStr = field(repr=False)
    verifier: SecretStr = field(repr=False)
    state: SecretStr = field(repr=False)


def _require_status(response: httpx2.Response, expected: int) -> None:
    # OAuth/admin response bodies can contain credentials. Never print them.
    assert response.status_code == expected, (
        f"Ory test request returned {response.status_code} - expected {expected}."
    )


def _single_query_value(url: str, name: str) -> str:
    values = parse_qs(urlsplit(url).query).get(name, [])
    assert len(values) == 1, f"Expected one {name} value in the test redirect."
    return values[0]


def _challenge(response: httpx2.Response, phase: str) -> str:
    assert response.status_code in {302, 303}
    location = response.headers["location"]
    parsed = urlsplit(location)
    expected = (
        f"{KRATOS_PUBLIC_URL}/self-service/login/browser"
        if phase == "login"
        else f"{UI_ORIGIN}/consent"
    )
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == expected
    return _single_query_value(location, f"{phase}_challenge")


def _hydra_redirect(response: httpx2.Response, *, public_url: str = HYDRA_PUBLIC_URL) -> str:
    _require_status(response, 200)
    location = _RedirectResponse.model_validate_json(response.text).redirect_to.get_secret_value()
    parsed = urlsplit(location)
    assert f"{parsed.scheme}://{parsed.netloc}" == public_url
    assert parsed.path == "/oauth2/auth"
    return location


def _raise_for_oauth_error(
    response: httpx2.Response, *, state: SecretStr, redirect_uri: str = REDIRECT_URI
) -> None:
    """Recognize a provider rejection only at our state-bound callback."""
    if response.status_code not in {302, 303}:
        return
    location = response.headers.get("location", "")
    parsed = urlsplit(location)
    if f"{parsed.scheme}://{parsed.netloc}{parsed.path}" != redirect_uri:
        return
    params = parse_qs(parsed.query)
    if "error" not in params:
        return
    assert secrets.compare_digest(_single_query_value(location, "state"), state.get_secret_value())
    assert "code" not in params
    errors = params["error"]
    assert len(errors) == 1
    assert errors[0] in {"invalid_request", "invalid_grant", "access_denied", "error"}, (
        "Hydra returned an unexpected OAuth error category."
    )
    raise HydraAuthorizationRejectedError(errors[0])


class HydraTestProvider:
    """Exercise real provider HTTP APIs on the private test network."""

    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        client_id: str = CLIENT_ID,
        endpoints: HydraTestEndpointsDTO = DEFAULT_HYDRA_ENDPOINTS,
        redirect_uri: str = REDIRECT_URI,
        kratos_public_url: str = KRATOS_PUBLIC_URL,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._endpoints = endpoints
        self._redirect_uri = redirect_uri
        self._kratos_public_url = kratos_public_url

    async def begin_login(
        self,
        human: RegisteredHumanDTO,
        *,
        include_audience: bool = True,
        browser: httpx2.AsyncClient | None = None,
        pkce: PKCEChallenge = "S256",
    ) -> PendingHydraLoginDTO:
        """Verify Kratos once, then stop before approving the Hydra login.

        Resuming this test flow does not recheck Kratos. That deliberately models
        an approval which was prepared before cleanup and submitted afterward.
        """
        whoami = await self._client.get(
            f"{self._kratos_public_url}/sessions/whoami",
            headers={"Cookie": f"ory_kratos_session={human.credential.value}"},
        )
        assert whoami.status_code == 200, (
            f"Kratos session check at {self._kratos_public_url} returned "
            f"{whoami.status_code} - expected 200."
        )
        subject = IdentitySubject(str(WhoamiResponse.model_validate_json(whoami.text).identity.id))
        assert subject == human.subject

        return await self._start_login(
            subject, include_audience=include_audience, browser=browser, pkce=pkce
        )

    async def _start_login(
        self,
        subject: IdentitySubject,
        *,
        include_audience: bool,
        browser: httpx2.AsyncClient | None,
        pkce: PKCEChallenge = "S256",
    ) -> PendingHydraLoginDTO:
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            # This increment exercises OAuth access/refresh tokens, not an ID token.
            "scope": "inframeld:api offline_access",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if include_audience:
            params["audience"] = API_AUDIENCE.value
        if pkce == "missing":
            del params["code_challenge"]
            del params["code_challenge_method"]
        elif pkce in {"plain", "missing_method"}:
            params["code_challenge"] = verifier
            if pkce == "plain":
                params["code_challenge_method"] = "plain"
            else:
                del params["code_challenge_method"]

        public = browser if browser is not None else self._client
        started = await public.get(f"{self._endpoints.public_url}/oauth2/auth", params=params)
        _raise_for_oauth_error(started, state=SecretStr(state), redirect_uri=self._redirect_uri)
        login_challenge = _challenge(started, "login")
        login = await self._read_login(login_challenge)
        if login.skip:
            assert login.subject == subject.value

        return PendingHydraLoginDTO(
            subject=subject,
            client_id=self._client_id,
            login_session_id=login.session_id,
            include_audience=include_audience,
            challenge=SecretStr(login_challenge),
            verifier=SecretStr(verifier),
            state=SecretStr(state),
        )

    async def begin_native_consent(
        self, human: RegisteredHumanDTO, *, browser: httpx2.AsyncClient
    ) -> PendingHydraConsentDTO:
        """Let real Kratos authenticate and approve login, without private login approval."""
        pending = await self._start_login(human.subject, include_audience=True, browser=browser)
        started = await browser.get(
            f"{KRATOS_PUBLIC_URL}/self-service/login/browser",
            params={"login_challenge": pending.challenge.get_secret_value()},
            headers={"Accept": "text/html"},
        )
        assert started.status_code in {302, 303}, "Native Kratos login did not redirect."
        location = started.headers["location"]
        parsed = urlsplit(location)
        if f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{KRATOS_PUBLIC_URL}/login":
            flow_id = str(UUID(_single_query_value(location, "flow")))
            read = await browser.get(
                f"{KRATOS_PUBLIC_URL}/self-service/login/flows",
                params={"id": flow_id},
                headers={"Accept": "application/json"},
            )
            _require_status(read, 200)
            flow = BrowserFlow.model_validate_json(read.text)
            action = urlsplit(flow.ui.action)
            assert (
                f"{action.scheme}://{action.netloc}{action.path}"
                == f"{KRATOS_PUBLIC_URL}/self-service/login"
            )
            submitted = await browser.post(
                flow.ui.action,
                data={
                    "csrf_token": read_browser_csrf_token(flow),
                    "identifier": human.email,
                    "password": human.password,
                    "method": "password",
                },
                headers={"Accept": "text/html"},
            )
            assert submitted.status_code in {302, 303}, "Native password login did not redirect."
            location = submitted.headers["location"]
        parsed = urlsplit(location)
        assert (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            == f"{self._endpoints.public_url}/oauth2/auth"
        )
        consent_redirect = await browser.get(location)
        challenge = _challenge(consent_redirect, "consent")
        response = await self._client.get(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/consent",
            params={"consent_challenge": challenge},
        )
        _require_status(response, 200)
        consent = _ConsentRequest.model_validate_json(response.text)
        assert consent.subject == human.subject.value
        assert consent.client.client_id == self._client_id
        assert consent.login_session_id == pending.login_session_id
        return PendingHydraConsentDTO(
            client_id=self._client_id,
            challenge=SecretStr(challenge),
            verifier=pending.verifier,
            state=pending.state,
            consent_skipped=consent.skip,
        )

    async def finish_native_consent(
        self, pending: PendingHydraConsentDTO, redirect_to: str, *, browser: httpx2.AsyncClient
    ) -> HydraAuthorizationCodeDTO:
        assert pending.client_id == self._client_id
        parsed = urlsplit(redirect_to)
        assert (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            == f"{self._endpoints.public_url}/oauth2/auth"
        )
        response = await browser.get(redirect_to)
        assert response.status_code in {302, 303}
        callback = response.headers["location"]
        parsed = urlsplit(callback)
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == self._redirect_uri
        assert secrets.compare_digest(
            _single_query_value(callback, "state"), pending.state.get_secret_value()
        )
        errors = parse_qs(parsed.query).get("error", [])
        category = (
            errors[0]
            if len(errors) == 1
            and errors[0]
            in {
                "error",
                "server_error",
                "access_denied",
                "invalid_request",
                "login_required",
                "consent_required",
            }
            else "unrecognized"
        )
        assert not errors, f"Hydra rejected native consent with error category '{category}'."
        return HydraAuthorizationCodeDTO(
            client_id=self._client_id,
            code=SecretStr(_single_query_value(callback, "code")),
            verifier=pending.verifier,
            consent_skipped=pending.consent_skipped,
        )

    async def approve_login_and_consent(
        self,
        pending: PendingHydraLoginDTO,
        *,
        browser: httpx2.AsyncClient | None = None,
        remember_login: bool = False,
        remember_consent: bool = False,
        credential_binding: HumanOAuthCredentialBindingDTO | None = None,
    ) -> HydraAuthorizationCodeDTO:
        """Approve the pending test flow and stop before exchanging its code.

        Continue with the same browser cookie jar used by begin_login().
        """
        public = browser if browser is not None else self._client
        flow = await self._approve_login(pending, public=public, remember_login=remember_login)
        consent = flow.consent
        payload: dict[str, object] = {
            "grant_scope": consent.requested_scope,
            "grant_access_token_audience": consent.requested_access_token_audience,
            "remember": remember_consent,
        }
        if credential_binding is not None:
            assert credential_binding.identity.subject.value == consent.subject, (
                "Binding does not match the test subject."
            )
            payload["session"] = {
                "access_token": {
                    "inframeld_installation_id": str(credential_binding.installation_id.value),
                    "inframeld_credential_version": credential_binding.version.value,
                }
            }
        accepted_consent = await self._client.put(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/consent/accept",
            params={"consent_challenge": flow.challenge.get_secret_value()},
            json=payload,
        )
        callback_redirect = await public.get(
            _hydra_redirect(accepted_consent, public_url=self._endpoints.public_url)
        )
        _raise_for_oauth_error(callback_redirect, state=flow.state, redirect_uri=self._redirect_uri)
        assert callback_redirect.status_code in {302, 303}
        callback = callback_redirect.headers["location"]
        parsed_callback = urlsplit(callback)
        assert (
            f"{parsed_callback.scheme}://{parsed_callback.netloc}{parsed_callback.path}"
            == self._redirect_uri
        )
        assert secrets.compare_digest(
            _single_query_value(callback, "state"), flow.state.get_secret_value()
        )
        assert "error" not in parse_qs(parsed_callback.query)
        code = _single_query_value(callback, "code")

        return HydraAuthorizationCodeDTO(
            client_id=self._client_id,
            code=SecretStr(code),
            verifier=flow.verifier,
            consent_skipped=consent.skip,
        )

    async def exchange_authorization_code(
        self,
        authorization: HydraAuthorizationCodeDTO,
        *,
        omit_verifier: bool = False,
        redirect_uri: str | None = None,
    ) -> IssuedHydraTokensDTO | None:
        """Exchange once, returning None only for an explicit invalid-grant denial."""
        assert authorization.client_id == self._client_id
        payload = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri if redirect_uri is None else redirect_uri,
            "grant_type": "authorization_code",
            "code": authorization.code.get_secret_value(),
        }
        if not omit_verifier:
            payload["code_verifier"] = authorization.verifier.get_secret_value()
        exchanged = await self._client.post(
            f"{self._endpoints.public_url}/oauth2/token",
            data=payload,
        )
        if exchanged.status_code == 400:
            assert _OAuthError.model_validate_json(exchanged.text).error == "invalid_grant"
            return None
        _require_status(exchanged, 200)
        tokens = _TokenResponse.model_validate_json(exchanged.text)
        assert tokens.token_type.casefold() == "bearer"
        return IssuedHydraTokensDTO(
            access_token=HumanAccessTokenCredential(tokens.access_token.get_secret_value()),
            refresh_token=tokens.refresh_token,
            consent_skipped=authorization.consent_skipped,
        )

    async def issue_tokens(
        self,
        human: RegisteredHumanDTO,
        *,
        include_audience: bool = True,
        browser: httpx2.AsyncClient | None = None,
        remember_login: bool = False,
        remember_consent: bool = False,
        credential_binding: HumanOAuthCredentialBindingDTO | None = None,
    ) -> IssuedHydraTokensDTO:
        """Complete the staged S256 test exchange without retrying provider failures.

        The production CLI still needs its OAuth/OIDC library, callback listener,
        ID-token validation and account UI integration.
        """
        pending = await self.begin_login(human, include_audience=include_audience, browser=browser)
        code = await self.approve_login_and_consent(
            pending,
            browser=browser,
            remember_login=remember_login,
            remember_consent=remember_consent,
            credential_binding=credential_binding,
        )
        tokens = await self.exchange_authorization_code(code)
        assert tokens is not None, "Hydra rejected the test authorization code."
        return tokens

    async def _begin_consent(
        self,
        human: RegisteredHumanDTO,
        *,
        public: httpx2.AsyncClient,
        include_audience: bool,
        remember_login: bool,
    ) -> _ConsentFlow:
        pending = await self.begin_login(human, browser=public, include_audience=include_audience)
        return await self._approve_login(pending, public=public, remember_login=remember_login)

    async def _approve_login(
        self,
        pending: PendingHydraLoginDTO,
        *,
        public: httpx2.AsyncClient,
        remember_login: bool,
    ) -> _ConsentFlow:
        assert pending.client_id == self._client_id
        accepted_login = await self._client.put(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/login/accept",
            params={"login_challenge": pending.challenge.get_secret_value()},
            json={"subject": pending.subject.value, "remember": remember_login},
        )
        consent_redirect = await public.get(
            _hydra_redirect(accepted_login, public_url=self._endpoints.public_url)
        )
        _raise_for_oauth_error(
            consent_redirect, state=pending.state, redirect_uri=self._redirect_uri
        )
        consent_challenge = _challenge(consent_redirect, "consent")

        consent_response = await self._client.get(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/consent",
            params={"consent_challenge": consent_challenge},
        )
        _require_status(consent_response, 200)
        consent = _ConsentRequest.model_validate_json(consent_response.text)
        assert consent.client.client_id == self._client_id
        assert consent.subject == pending.subject.value
        assert consent.login_session_id == pending.login_session_id
        assert set(consent.requested_scope) == {"inframeld:api", "offline_access"}
        expected_audience = [API_AUDIENCE.value] if pending.include_audience else []
        assert consent.requested_access_token_audience == expected_audience

        return _ConsentFlow(
            consent=consent,
            challenge=SecretStr(consent_challenge),
            verifier=pending.verifier,
            state=pending.state,
        )

    async def remember_login_without_consent(
        self, human: RegisteredHumanDTO, *, browser: httpx2.AsyncClient
    ) -> None:
        """Remember a verified login, then decline consent without issuing tokens."""
        flow = await self._begin_consent(
            human, public=browser, include_audience=True, remember_login=True
        )
        rejected = await self._client.put(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/consent/reject",
            params={"consent_challenge": flow.challenge.get_secret_value()},
            json={"error": "access_denied", "error_description": "Test consent declined"},
        )
        returned = await browser.get(
            _hydra_redirect(rejected, public_url=self._endpoints.public_url)
        )
        assert returned.status_code in {302, 303}
        callback = returned.headers["location"]
        parsed = urlsplit(callback)
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == self._redirect_uri
        assert _single_query_value(callback, "error") == "access_denied"
        assert secrets.compare_digest(
            _single_query_value(callback, "state"), flow.state.get_secret_value()
        )

    async def _read_login(self, challenge: str) -> _LoginRequest:
        response = await self._client.get(
            f"{self._endpoints.admin_url}/admin/oauth2/auth/requests/login",
            params={"login_challenge": challenge},
        )
        _require_status(response, 200)
        return _LoginRequest.model_validate_json(response.text)

    async def refresh_tokens(self, tokens: IssuedHydraTokensDTO) -> IssuedHydraTokensDTO | None:
        """Return rotated credentials, or None for an explicit invalid-grant denial."""
        response = await self._client.post(
            f"{self._endpoints.public_url}/oauth2/token",
            data={
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token.get_secret_value(),
            },
        )
        if response.status_code == 400:
            assert _OAuthError.model_validate_json(response.text).error == "invalid_grant"
            return None
        _require_status(response, 200)
        refreshed = _TokenResponse.model_validate_json(response.text)
        assert refreshed.token_type.casefold() == "bearer"
        return IssuedHydraTokensDTO(
            access_token=HumanAccessTokenCredential(refreshed.access_token.get_secret_value()),
            refresh_token=refreshed.refresh_token,
            consent_skipped=tokens.consent_skipped,
        )

    async def token_is_active(self, credential: HumanAccessTokenCredential) -> bool:
        response = await self._client.post(
            f"{self._endpoints.admin_url}/admin/oauth2/introspect",
            data={"token": credential.value, "token_type_hint": "access_token"},
        )
        _require_status(response, 200)
        return _IntrospectionResponse.model_validate_json(response.text).active

    async def assert_token_binding(
        self, credential: HumanAccessTokenCredential, *, binding: HumanOAuthCredentialBindingDTO
    ) -> None:
        """Check only the expected identity and server-owned metadata, without printing tokens."""
        response = await self._client.post(
            f"{self._endpoints.admin_url}/admin/oauth2/introspect",
            data={"token": credential.value, "token_type_hint": "access_token"},
        )
        _require_status(response, 200)
        observed = _BoundIntrospectionResponse.model_validate_json(response.text)
        assert observed.active
        assert observed.iss == f"{self._endpoints.public_url}/"
        assert observed.sub == binding.identity.subject.value
        assert observed.client_id == self._client_id
        assert observed.aud == [API_AUDIENCE.value]
        assert observed.ext.inframeld_installation_id == binding.installation_id.value
        assert observed.ext.inframeld_credential_version == binding.version.value

    async def revoke_refresh_token(self, token: SecretStr) -> None:
        """Request selected-login revocation once, leaving its effect for the test to verify."""
        response = await self._client.post(
            f"{self._endpoints.public_url}/oauth2/revoke",
            data={
                "client_id": self._client_id,
                "token": token.get_secret_value(),
                "token_type_hint": "refresh_token",
            },
        )
        _require_status(response, 200)

    async def login_can_skip(self, browser: httpx2.AsyncClient) -> bool:
        """Observe a fresh login challenge without approving it or issuing more tokens."""
        started = await browser.get(
            f"{self._endpoints.public_url}/oauth2/auth",
            params={
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "inframeld:api offline_access",
                "audience": API_AUDIENCE.value,
                "state": secrets.token_urlsafe(32),
                "code_challenge": secrets.token_urlsafe(32),
                "code_challenge_method": "S256",
            },
        )
        return (await self._read_login(_challenge(started, "login"))).skip

    async def revoke_access_token(self, credential: HumanAccessTokenCredential) -> None:
        response = await self._client.post(
            f"{self._endpoints.public_url}/oauth2/revoke",
            data={
                "client_id": self._client_id,
                "token": credential.value,
                "token_type_hint": "access_token",
            },
        )
        _require_status(response, 200)


@asynccontextmanager
async def hydra_test_provider(
    *,
    client_id: str = CLIENT_ID,
    transport: httpx2.AsyncBaseTransport | None = None,
    kratos_public_url: str = KRATOS_PUBLIC_URL,
) -> AsyncGenerator[HydraTestProvider]:
    """Own one test client registration and remove it even after a scenario fails.

    This runs only against the dedicated Hydra test database. Tests using this
    same registered client must run sequentially.
    """
    http_logger = logging.getLogger("httpx2")
    previous_level = http_logger.level
    http_logger.setLevel(logging.WARNING)
    try:
        async with httpx2.AsyncClient(
            timeout=5.0,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            client_url = f"{HYDRA_ADMIN_URL}/admin/clients/{client_id}"
            removed = await client.delete(client_url)
            assert removed.status_code in {204, 404}
            created = await client.post(
                f"{HYDRA_ADMIN_URL}/admin/clients",
                json={
                    "client_id": client_id,
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
                yield HydraTestProvider(
                    client, client_id=client_id, kratos_public_url=kratos_public_url
                )
            finally:
                _require_status(await client.delete(client_url), 204)
    finally:
        http_logger.setLevel(previous_level)
