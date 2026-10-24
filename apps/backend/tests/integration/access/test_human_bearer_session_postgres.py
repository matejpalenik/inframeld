"""Exercise human bearer authentication through HTTP and real PostgreSQL reads."""

import os
from functools import partial
from typing import Literal, override
from uuid import uuid4

import httpx2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, update
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
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
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_block_reader import (
    PostgresIdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
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

    def __init__(self, database: Database) -> None:
        self.database = database
        self.tokens = {TOKEN: HumanCredentialVersion(1)}
        self.calls = 0
        self.unavailable = False

    @override
    async def verify(
        self,
        credential: HumanAccessTokenCredential,
        *,
        timeout_seconds: float,
    ) -> HumanOAuthCredentialBindingDTO | None:
        self.calls += 1

        if self.unavailable:
            raise DependencyUnavailableError()

        version = self.tokens.get(credential)
        if version is None:
            return None
        installation = await PostgresInstallationIdentityReader(self.database).read()
        return HumanOAuthCredentialBindingDTO(IDENTITY, installation, version)


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
        recovery_block_reader = PostgresIdentityRecoveryBlockReader(api_database)

        self.token = MockTokenVerifier(api_database)
        self.identity = MockIdentityVerifier()
        self.browser = MockBrowserVerifier()

        authenticate = HumanSessionDependency(
            HumanSessionAuthenticationService(
                self.browser, reader, recovery_block_reader=recovery_block_reader
            ),
            CSRFProtectionDependency(()),
            access_token_authenticator=HumanAccessTokenAuthenticationService(
                self.token,
                self.identity,
                reader,
                credential_state_reader=PostgresHumanCredentialStateReader(api_database),
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


async def _admit_recovery(database: Database) -> OperationId:
    installation_id = await PostgresInstallationIdentityReader(database).read()
    event = IdentityRecoveryEventDTO(
        flow_id=IdentityRecoveryFlowId(uuid4()),
        identity=IDENTITY,
        event_kind=IdentityRecoveryEventKind.RECOVERY,
    )
    async with database.session() as session, session.begin():
        return await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=installation_id,
                authority=IDENTITY.authority,
            )
        ).admit(event)


async def _seed_recovery_outcome(
    database: Database, operation_id: OperationId, *, release_block: bool
) -> None:
    """Arrange cleanup state directly without claiming real provider cleanup."""
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                released_at=func.now() if release_block else None,
            )
        )


def _get_session(client: TestClient, family: Literal["cookie", "bearer"]) -> httpx2.Response:
    client.cookies.clear()
    if family == "cookie":
        client.cookies.set("ory_kratos_session", COOKIE.value)
        return client.get("/v1/session")
    return client.get("/v1/session", headers=BEARER_HEADERS)


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["cookie", "bearer"])
async def test_recovery_block_changes_are_enforced_on_the_next_http_request(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    linked_human: Principal,
    family: Literal["cookie", "bearer"],
) -> None:
    """Each credential follows committed recovery state without clearing suspension."""
    fresh = HumanAccessTokenCredential("synthetic-fresh-human-token")
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = _get_session(client, family)
        assert first.status_code == 200, first.text
        assert first.json() == {"principalId": str(linked_human.id.value)}

        operation_id = await _admit_recovery(database)
        blocked = _get_session(client, family)
        assert blocked.status_code == (401 if family == "bearer" else 403), blocked.text
        assert blocked.json()["code"] == ("http_error" if family == "bearer" else "access_denied")

        await _seed_recovery_outcome(database, operation_id, release_block=False)
        unreleased = _get_session(client, family)
        assert unreleased.status_code == (401 if family == "bearer" else 403), unreleased.text

        await _seed_recovery_outcome(database, operation_id, release_block=True)
        released = _get_session(client, family)
        if family == "bearer":
            assert released.status_code == 401
            # Model a fresh provider grant explicitly, not an upgrade of the old one.
            scenario.token.tokens[fresh] = HumanCredentialVersion(2)
            released = client.get("/v1/session", headers={"Authorization": f"Bearer {fresh.value}"})
        assert released.status_code == 200, released.text
        assert released.json() == {"principalId": str(linked_human.id.value)}

        async with database.session() as session, session.begin():
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == linked_human.id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )

        suspended = (
            client.get("/v1/session", headers={"Authorization": f"Bearer {fresh.value}"})
            if family == "bearer"
            else _get_session(client, family)
        )
        assert suspended.status_code == 403, suspended.text
        assert suspended.json()["code"] == "access_denied"


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["cookie", "bearer"])
async def test_later_local_admission_does_not_bypass_an_existing_recovery_block(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    family: Literal["cookie", "bearer"],
) -> None:
    """Linking a new local account cannot remove its provider identity's pending block."""
    await _admit_recovery(database)
    scenario = SessionScenario(temporary_postgres_settings)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        before_link = _get_session(client, family)
        assert before_link.status_code == (401 if family == "bearer" else 403), before_link.text

        async with database.session() as session, session.begin():
            principal = await MockAccessScenarios.seed_linked_human(session, IDENTITY)

        assert principal.status is PrincipalStatus.ACTIVE
        after_link = _get_session(client, family)

    assert after_link.status_code == (401 if family == "bearer" else 403), after_link.text
    assert after_link.json()["code"] == ("http_error" if family == "bearer" else "access_denied")


@pytest_asyncio.fixture(autouse=True)
async def versioned_test_credentials(database: Database) -> None:
    """Seed the security metadata represented by the mocked provider's fixed grant."""
    await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
