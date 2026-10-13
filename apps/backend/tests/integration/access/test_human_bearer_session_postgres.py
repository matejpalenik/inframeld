"""Exercise human bearer authentication through HTTP and real PostgreSQL reads."""

import os
from functools import partial
from typing import Literal, override

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
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
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"),
    subject=IdentitySubject("00000000-0000-4000-8000-000000000003"),
)
TOKEN = HumanAccessTokenCredential("synthetic-human-token")
COOKIE = BrowserSessionCredential("synthetic-browser-session")
BEARER_HEADERS = {"Authorization": f"Bearer {TOKEN.value}"}


class MockTokenVerifier(HumanAccessTokenVerifier):
    """Represent Hydra responses without replacing the real authentication workflow."""

    def __init__(self) -> None:
        self.calls = 0
        self.unavailable = False

    @override
    async def verify(
        self,
        credential: HumanAccessTokenCredential,
        *,
        timeout_seconds: float,
    ) -> VerifiedHumanIdentityDTO | None:
        self.calls += 1

        if self.unavailable:
            raise DependencyUnavailableError()

        return IDENTITY if credential == TOKEN else None


class MockIdentityVerifier(HumanIdentityVerifier):
    """Allow a test to disable the identity or interrupt its current eligibility check."""

    def __init__(self) -> None:
        self.calls = 0
        self.eligible = True
        self.unavailable = False

    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        self.calls += 1

        if self.unavailable:
            raise DependencyUnavailableError()

        return identity if self.eligible and identity == IDENTITY else None


class MockBrowserVerifier(BrowserSessionVerifier):
    """Give the cookie path the same verified external identity as the bearer path."""

    def __init__(self) -> None:
        self.calls = 0

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        self.calls += 1
        return IDENTITY if credential == COOKIE else None


class SessionScenario:
    """Assemble production authentication and routing with controllable provider results"""

    def __init__(self, settings: DatabaseSettings) -> None:
        # `TestClient` uses its own event loop so it needs its own db pool
        api_database = Database(settings)
        reader = PostgresHumanIdentityLinkReader(api_database)

        self.token = MockTokenVerifier()
        self.identity = MockIdentityVerifier()
        self.browser = MockBrowserVerifier()

        authenticate = HumanSessionDependency(
            HumanSessionAuthenticationService(self.browser, reader),
            CSRFProtectionDependency(()),
            access_token_authenticator=HumanAccessTokenAuthenticationService(
                self.token, self.identity, reader
            ),
        )

        self.application = FastAPI(
            lifespan=partial(application_lifespan, ApplicationResources(database=api_database))
        )

        register_error_handlers(self.application)
        configure_problem_openapi(self.application)
        self.application.include_router(create_session_router(authenticate))
        self.application.add_middleware(RequestContextMiddleware)


@pytest_asyncio.fixture
async def linked_human(database: Database) -> Principal:
    """Commit Alice's identity link before the app reads it through a separate connection."""
    async with database.session() as session, session.begin():
        return await MockAccessScenarios.seed_linked_human(session, IDENTITY)


@pytest.mark.asyncio
async def test_cookie_and_bearer_resolve_the_same_local_human(
    temporary_postgres_settings: DatabaseSettings, linked_human: Principal
) -> None:
    """Changing the login mechanism must not create or select a different local account."""

    scenario = SessionScenario(temporary_postgres_settings)
    expected = {"principalId": str(linked_human.id.value)}

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        client.cookies.set("ory_kratos_session", COOKIE.value)
        cookie_response = client.get("/v1/session")

        assert cookie_response.status_code == 200, cookie_response.text
        assert cookie_response.json() == expected

        client.cookies.clear()

        bearer_response = client.get("/v1/session", headers=BEARER_HEADERS)
        assert bearer_response.status_code == 200, bearer_response.text
        assert bearer_response.json() == expected

    assert scenario.browser.calls == 1
    assert scenario.token.calls == 1
    assert scenario.identity.calls == 1


@pytest.mark.asyncio
async def test_next_bearer_request_reads_local_suspension(
    database: Database, temporary_postgres_settings: DatabaseSettings, linked_human: Principal
) -> None:
    """A previously valid token cannot bypass a suspension committed after its last request."""
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = client.get("/v1/session", headers=BEARER_HEADERS)

        assert first.status_code == 200, first.text

        # Suspend a principal in the DB
        async with database.session() as session, session.begin():
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == linked_human.id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )

        second = client.get("/v1/session", headers=BEARER_HEADERS)

    assert second.status_code == 403, second.text
    assert second.json()["code"] == "access_denied"
    assert scenario.token.calls == 2
    assert scenario.identity.calls == 2
    assert scenario.browser.calls == 0


@pytest.mark.asyncio
async def test_next_bearer_request_rechecks_kratos_eligibility(
    temporary_postgres_settings: DatabaseSettings,
    linked_human: Principal,
) -> None:
    """A current token is rejected when Kratos stops admitting its identity."""
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = client.get("/v1/session", headers=BEARER_HEADERS)
        assert first.status_code == 200, first.text
        assert first.json() == {"principalId": str(linked_human.id.value)}

        # Simulate Kratos not admitting an identity
        scenario.identity.eligible = False
        second = client.get("/v1/session", headers=BEARER_HEADERS)

    assert second.status_code == 401, second.text
    assert second.json()["code"] == "http_error"
    assert second.headers["WWW-Authenticate"] == ('Bearer realm="inframeld", error="invalid_token"')

    assert scenario.token.calls == 2
    assert scenario.identity.calls == 2
    assert scenario.browser.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["hydra", "kratos"])
async def test_provider_outage_cannot_reuse_an_earlier_success(
    temporary_postgres_settings: DatabaseSettings,
    linked_human: Principal,
    provider: Literal["hydra", "kratos"],
) -> None:
    """Losing either provider must stop the next request instead of trusting an old success."""

    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = client.get("/v1/session", headers=BEARER_HEADERS)
        assert first.status_code == 200, first.text
        assert first.json() == {"principalId": str(linked_human.id.value)}

        if provider == "hydra":
            scenario.token.unavailable = True
        else:
            scenario.identity.unavailable = True

        second = client.get("/v1/session", headers=BEARER_HEADERS)

    assert second.status_code == 503, second.text
    assert second.json()["code"] == "dependency_unavailable"
    assert "WWW-Authenticate" not in second.headers
    assert scenario.token.calls == 2
    assert scenario.identity.calls == (1 if provider == "hydra" else 2)
    assert scenario.browser.calls == 0


@pytest.mark.asyncio
async def test_verified_identity_without_local_admission_is_denied(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Provider approval alone cannot admit a human who has no local identity link."""
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        response = client.get("/v1/session", headers=BEARER_HEADERS)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"
    assert scenario.token.calls == 1
    assert scenario.identity.calls == 1
    assert scenario.browser.calls == 0
    assert await PostgresHumanIdentityLinkReader(database).find_principal(IDENTITY) is None


@pytest.mark.asyncio
async def test_competing_credentials_are_rejected_before_provider_verification(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Do not choose between credentials, even when they could identify the same human."""
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        client.cookies.set("ory_kratos_session", COOKIE.value)
        response = client.get("/v1/session", headers=BEARER_HEADERS)

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_authentication_request"
    assert response.headers["WWW-Authenticate"] == (
        'Bearer realm="inframeld", error="invalid_request"'
    )
    assert scenario.token.calls == 0
    assert scenario.identity.calls == 0
    assert scenario.browser.calls == 0
    assert await PostgresHumanIdentityLinkReader(database).find_principal(IDENTITY) is None
