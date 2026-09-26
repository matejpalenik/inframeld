"""Check human session authentication through a real FastAPI request boundary."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.application.human_session import (
    HumanIdentityLinkReader,
    HumanSessionResolver,
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.values import (
    IdentityAuthority,
    IdentitySubject,
    PrincipalId,
)
from inframeld_backend.access.http.human_session_authentication import HumanSessionAuthentication
from inframeld_backend.shared.application.errors import DependencyUnavailableError
from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.request_context import RequestContextMiddleware

IDENTITY = VerifiedHumanIdentity(
    authority=IdentityAuthority("kratos:test"),
    subject=IdentitySubject("00000000-0000-0000-0000-000000000001"),
)
PRINCIPAL_ID = PrincipalId(UUID("00000000-0000-0000-0000-000000000002"))
COOKIE_NAME = "ory_kratos_session"


class _MockVerifier:
    """Return a chosen verified identity or provider failure while recording calls."""

    def __init__(
        self,
        identity: VerifiedHumanIdentity | None,
        failure: Exception | None = None,
    ) -> None:
        """Choose the identity or failure to return for a request."""
        self.identity = identity
        self.failure = failure
        self.seen_cookies: list[str] = []

    async def __call__(self, cookie: str) -> VerifiedHumanIdentity | None:
        """Record the cookie received by the authentication boundary."""
        self.seen_cookies.append(cookie)
        if self.failure is not None:
            raise self.failure
        return self.identity


class _MockLinkReader(HumanIdentityLinkReader):
    """Resolve a chosen local principal while recording identity lookups."""

    def __init__(self, principal_id: PrincipalId | None) -> None:
        """Choose whether the verified identity has an active local link."""
        self.principal_id = principal_id
        self.seen_identities: list[VerifiedHumanIdentity] = []

    async def find_active_principal_id(self, identity: VerifiedHumanIdentity) -> PrincipalId | None:
        """Record the exact authority and subject used for local lookup."""
        self.seen_identities.append(identity)
        return self.principal_id


def _test_app(verifier: _MockVerifier, reader: _MockLinkReader) -> FastAPI:
    """Expose one protected test route using the production HTTP dependency."""
    application = FastAPI(debug=False)
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    authenticate = HumanSessionAuthentication(verifier, HumanSessionResolver(reader))

    @application.get("/_test/protected")
    async def protected(
        access: Annotated[AccessContext, Depends(authenticate)],
    ) -> dict[str, str]:
        """Return the principal admitted by human session authentication."""
        return {"principalId": str(access.actor_principal_id)}

    return application


def test_valid_session_resolves_local_principal() -> None:
    """Admit the exact local principal linked to a verified browser identity."""
    verifier = _MockVerifier(IDENTITY)
    reader = _MockLinkReader(PRINCIPAL_ID)

    with TestClient(_test_app(verifier, reader), raise_server_exceptions=False) as client:
        client.cookies.set(COOKIE_NAME, "valid-session")
        response = client.get("/_test/protected")

    assert response.status_code == 200
    assert response.json() == {"principalId": str(PRINCIPAL_ID)}
    assert verifier.seen_cookies == ["valid-session"]
    assert reader.seen_identities == [IDENTITY]


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
