"""Check human session authentication through a real FastAPI request boundary."""

from typing import Annotated, override
from uuid import UUID

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
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
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


def _test_app(verifier: _MockVerifier, reader: _MockLinkReader) -> FastAPI:
    """Expose one protected test route using the production HTTP dependency."""
    application = FastAPI(debug=False)
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    authenticate = HumanSessionDependency(
        HumanSessionAuthenticationService(verifier, reader),
        CSRFProtectionDependency(TRUSTED_ORIGINS),
    )

    @application.get("/_test/protected")
    async def protected(
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> dict[str, str]:
        """Return the principal admitted by human session authentication."""
        return {"principalId": str(access.actor_principal_id.value)}

    return application


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
