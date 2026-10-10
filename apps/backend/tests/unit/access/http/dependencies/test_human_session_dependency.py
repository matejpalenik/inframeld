"""Check human session authentication through a real FastAPI request boundary."""

from typing import Annotated, override
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"),
    subject=IdentitySubject("00000000-0000-0000-0000-000000000001"),
)
PRINCIPAL_ID = PrincipalId(UUID("00000000-0000-0000-0000-000000000002"))
COOKIE_NAME = "ory_kratos_session"
TRUSTED_ORIGINS: tuple[HttpUrl, ...] = (HttpUrl("http://testserver"),)
TOKEN = "opaque-human-token"


class _MockVerifier(BrowserSessionVerifier):
    """Return a chosen verified identity or provider failure while recording calls."""

    def __init__(
        self,
        identity: VerifiedHumanIdentityDTO | None,
        failure: Exception | None = None,
    ) -> None:
        """Choose the identity or failure to return for a request."""
        self.identity = identity
        self.failure = failure
        self.seen_cookies: list[str] = []

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        """Record the cookie received by the authentication boundary."""
        self.seen_cookies.append(credential.value)
        if self.failure is not None:
            raise self.failure
        return self.identity


class _MockLinkReader(HumanIdentityLinkReader):
    """Resolve a chosen local principal while recording identity lookups."""

    def __init__(self, principal_id: PrincipalId | None) -> None:
        """Choose whether the verified identity has an active local link."""
        self.principal_id = principal_id
        self.seen_identities: list[VerifiedHumanIdentityDTO] = []

    @override
    async def find_principal(self, identity: VerifiedHumanIdentityDTO) -> Principal | None:
        """Record the exact authority and subject used for local lookup."""
        self.seen_identities.append(identity)
        return (
            Principal(
                self.principal_id,
                OrganizationId(UUID(int=1)),
                PrincipalKind.HUMAN,
                PrincipalStatus.ACTIVE,
            )
            if self.principal_id is not None
            else None
        )


def _test_app(
    verifier: _MockVerifier,
    reader: _MockLinkReader,
    bearer: HumanAccessTokenAuthenticator | None = None,
) -> FastAPI:
    """Expose protected reads and writes using the production HTTP dependency."""
    application = FastAPI(debug=False)
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    authenticate = HumanSessionDependency(
        HumanSessionAuthenticationService(verifier, reader),
        CSRFProtectionDependency(TRUSTED_ORIGINS),
        access_token_authenticator=bearer,
    )

    @application.get("/_test/protected")
    async def protected(
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> dict[str, str]:
        """Return the principal admitted by human authentication."""
        return {"principalId": str(access.actor_principal_id.value)}

    @application.post("/_test/protected")
    async def protected_write(
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> dict[str, str]:
        return {"principalId": str(access.actor_principal_id.value)}

    return application


class _RecordingAccessTokenAuthenticator(HumanAccessTokenAuthenticator):
    """Record bearer calls and simulate the application operation's outcome."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.seen_tokens: list[HumanAccessTokenCredential] = []

    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError
        self.seen_tokens.append(credential)
        if self.failure is not None:
            raise self.failure
        return AccessContextDTO(actor_principal_id=PRINCIPAL_ID)


def test_valid_session_resolves_local_principal() -> None:
    """Admit the exact local principal linked to a verified browser identity."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "valid-session")
        response = client.get("/_test/protected")

    assert response.status_code == 200
    assert response.json() == {"principalId": str(PRINCIPAL_ID.value)}
    assert verifier.seen_cookies == ["valid-session"]
    assert reader.seen_identities == [IDENTITY]


def test_cookie_authenticated_post_requires_csrf_header() -> None:
    """Reject a browser write before its operation runs when the CSRF header is absent."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    application = _test_app(verifier, reader)
    authenticate = HumanSessionDependency(
        HumanSessionAuthenticationService(verifier, reader),
        CSRFProtectionDependency(TRUSTED_ORIGINS),
    )
    changes: list[PrincipalId] = []

    @application.post("/_test/change")
    async def change(access: Annotated[AccessContextDTO, Depends(authenticate)]) -> dict[str, bool]:
        changes.append(access.actor_principal_id)
        return {"changed": True}

    with TestClient(application, raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "valid-session")
        response = client.post("/_test/change", headers={"Origin": "http://testserver"})

    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert changes == []


def test_cookie_authenticated_post_rejects_untrusted_origin() -> None:
    """Reject a write from another origin even when it supplies the CSRF header."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    application = _test_app(verifier, reader)
    authenticate = HumanSessionDependency(
        HumanSessionAuthenticationService(verifier, reader),
        CSRFProtectionDependency(TRUSTED_ORIGINS),
    )
    changes: list[PrincipalId] = []

    @application.post("/_test/change")
    async def change(access: Annotated[AccessContextDTO, Depends(authenticate)]) -> dict[str, bool]:
        changes.append(access.actor_principal_id)
        return {"changed": True}

    with TestClient(application, raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "valid-session")
        response = client.post(
            "/_test/change", headers={"Origin": "https://attacker.example", "X-Inframeld-CSRF": "1"}
        )

    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert changes == []


def test_cookie_authenticated_post_accepts_trusted_origin() -> None:
    """Run a write when authentication, the CSRF header, and origin all pass."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    application = _test_app(verifier, reader)
    authenticate = HumanSessionDependency(
        HumanSessionAuthenticationService(verifier, reader),
        CSRFProtectionDependency(TRUSTED_ORIGINS),
    )
    changes: list[PrincipalId] = []

    @application.post("/_test/change")
    async def change(access: Annotated[AccessContextDTO, Depends(authenticate)]) -> dict[str, bool]:
        changes.append(access.actor_principal_id)
        return {"changed": True}

    with TestClient(application, raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "valid-session")
        response = client.post(
            "/_test/change", headers={"Origin": "http://testserver", "X-Inframeld-CSRF": "1"}
        )

    assert response.status_code == 200
    assert response.json() == {"changed": True}
    assert changes == [PRINCIPAL_ID]


def test_missing_session_is_unauthorized_without_provider_lookup() -> None:
    """Reject an absent browser cookie before contacting Kratos or PostgreSQL."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        response = client.get("/_test/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "http_error"
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []


def test_rejected_session_is_unauthorized_without_local_lookup() -> None:
    """Reject a cookie Kratos cannot verify without resolving a local identity."""
    verifier = _MockVerifier(None)
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "rejected-session")
        response = client.get("/_test/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "http_error"
    assert verifier.seen_cookies == ["rejected-session"]
    assert reader.seen_identities == []


def test_verified_identity_without_active_link_is_forbidden() -> None:
    """Deny a valid Kratos identity without an active local human principal."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(None)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "unlinked-session")
        response = client.get("/_test/protected")

    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"
    assert verifier.seen_cookies == ["unlinked-session"]
    assert reader.seen_identities == [IDENTITY]


def test_provider_failure_returns_unavailable_without_local_lookup() -> None:
    """Fail closed when Kratos cannot verify the browser session."""
    verifier = _MockVerifier(None, DependencyUnavailableError())
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "unverifiable-session")
        response = client.get("/_test/protected")

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert verifier.seen_cookies == ["unverifiable-session"]
    assert reader.seen_identities == []


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_human_bearer_uses_only_bearer_authentication(scheme: str, method: str) -> None:
    """Admit a human bearer request, including writes without cookie CSRF inputs."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.request(
            method, "/_test/protected", headers={"Authorization": f"{scheme} {TOKEN}"}
        )

    assert response.status_code == 200
    assert response.json() == {"principalId": str(PRINCIPAL_ID.value)}
    assert bearer.seen_tokens == [HumanAccessTokenCredential(TOKEN)]
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []


@pytest.mark.parametrize("cookie", ["valid-session", ""])
def test_cookie_and_authorization_are_rejected_before_authentication(cookie: str) -> None:
    """Reject competing mechanisms even when the supplied session cookie is empty."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        client.cookies.set(COOKIE_NAME, cookie)
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_authentication_request"
    assert response.headers["WWW-Authenticate"] == (
        'Bearer realm="inframeld", error="invalid_request"'
    )
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []


def test_duplicate_authorization_headers_are_rejected_before_authentication() -> None:
    """Never choose one of two Authorization values, even if both values are equal."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get(
            "/_test/protected",
            headers=[
                ("Authorization", f"Bearer {TOKEN}"),
                ("Authorization", f"Bearer {TOKEN}"),
            ],
        )

    assert response.status_code == 400
    problem = response.json()
    assert problem["type"].endswith("#invalid-authentication-request")
    assert problem["title"] == "Invalid authentication request"
    assert problem["code"] == "invalid_authentication_request"
    assert problem["detail"] == (
        "Use one supported authentication method with correctly formatted credentials."
    )
    assert problem["requestId"] == response.headers["X-Request-ID"]
    assert "instance" not in problem
    assert "errors" not in problem
    assert TOKEN not in response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["WWW-Authenticate"] == (
        'Bearer realm="inframeld", error="invalid_request"'
    )
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []


@pytest.mark.parametrize(
    ("authorization", "bearer_challenge"),
    [
        ("", False),
        ("Bearer", True),
        ("Bearer ", True),
        ("Bearer first second", True),
        ("Bearer first,second", True),
        ("Bearer\tcredential", True),
        ('Bearer "credential"', True),
    ],
)
def test_malformed_authorization_is_rejected_before_authentication(
    authorization: str, bearer_challenge: bool
) -> None:
    """Reject malformed header syntax before passing any credential to a service."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected", headers={"Authorization": authorization})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_authentication_request"
    if bearer_challenge:
        assert response.headers["WWW-Authenticate"] == (
            'Bearer realm="inframeld", error="invalid_request"'
        )
    else:
        assert "WWW-Authenticate" not in response.headers
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []


def test_missing_credentials_include_a_bearer_challenge() -> None:
    """Advertise the supported Bearer scheme without claiming a token was invalid."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "http_error"
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="inframeld"'
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []


@pytest.mark.parametrize("credential", ["ifm_app_invalid", "ifm_app_"])
def test_application_key_never_reaches_human_authenticators(credential: str) -> None:
    """Reject the application credential family on a human-only authentication path."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {credential}"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == (
        'Bearer realm="inframeld", error="invalid_token"'
    )
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []


def test_invalid_human_bearer_does_not_fall_back_to_browser_authentication() -> None:
    """A rejected human token ends authentication without trying another mechanism."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator(AuthenticationRequiredError())

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 401
    assert response.json()["code"] == "http_error"
    assert response.headers["WWW-Authenticate"] == (
        'Bearer realm="inframeld", error="invalid_token"'
    )
    assert bearer.seen_tokens == [HumanAccessTokenCredential(TOKEN)]
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
        (AccessDeniedError(), 403, "access_denied"),
    ],
)
def test_bearer_failures_preserve_application_outcomes(
    failure: Exception, status: int, code: str
) -> None:
    """Keep provider uncertainty and local admission denial distinct from invalid tokens."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator(failure)

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == status
    assert response.json()["code"] == code
    assert "WWW-Authenticate" not in response.headers
    assert bearer.seen_tokens == [HumanAccessTokenCredential(TOKEN)]
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []


def test_unconfigured_bearer_authentication_returns_unavailable() -> None:
    """A well-formed human token cannot be admitted when Hydra is unconfigured."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader)) as client:
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []


def test_unrelated_cookie_does_not_compete_with_human_bearer() -> None:
    """Only the Kratos session cookie competes with Authorization."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        client.cookies.set("theme", "dark")
        response = client.get("/_test/protected", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200
    assert bearer.seen_tokens == [HumanAccessTokenCredential(TOKEN)]
    assert verifier.seen_cookies == []


def test_unsupported_authorization_scheme_is_unauthorized() -> None:
    """A valid Basic header is an unsupported credential family, not a syntax error."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)
    bearer = _RecordingAccessTokenAuthenticator()

    with TestClient(_test_app(verifier, reader, bearer)) as client:
        response = client.get("/_test/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="inframeld"'
    assert verifier.seen_cookies == []
    assert reader.seen_identities == []
    assert bearer.seen_tokens == []
