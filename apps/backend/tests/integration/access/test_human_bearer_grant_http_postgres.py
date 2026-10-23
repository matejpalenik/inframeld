"""Verify authenticated grant writes, current authority, and denial without changes."""

import os
from dataclasses import dataclass
from functools import partial
from typing import Literal, override
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, select, update
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
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.http.routes.project_grant_routes import create_project_grant_router
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_block_reader import (
    PostgresIdentityRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.bootstrap.project_grant_composition import open_project_grant_change
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
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
TRUSTED_ORIGIN = "http://studio.test"


@dataclass(frozen=True, slots=True)
class GrantSeedDTO:
    """Identify the project, admitted Alice, and Bob targeted by the test command."""

    organization_id: OrganizationId
    project_id: ProjectId
    actor_id: PrincipalId
    recipient_id: PrincipalId
    action_id: ActionId


@dataclass(frozen=True, slots=True)
class ProjectGrantStateDTO:
    """Capture one current assignment without retaining an ORM row or session."""

    recipient_id: PrincipalId
    action_id: ActionId
    can_grant: bool


@dataclass(frozen=True, slots=True)
class GrantStateDTO:
    """Capture durable effects so denied requests can be checked for unintended writes."""

    project_grants: tuple[ProjectGrantStateDTO, ...]
    audit_count: int
    operation_ids: tuple[OperationId, ...]
    access_revision: int


class MockTokenVerifier(HumanAccessTokenVerifier):
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
    def __init__(self) -> None:
        self.calls = 0
        self.unavailable = False

    @override
    async def verify(
        self,
        identity: VerifiedHumanIdentityDTO,
        *,
        timeout_seconds: float,
    ) -> VerifiedHumanIdentityDTO | None:
        self.calls += 1
        if self.unavailable:
            raise DependencyUnavailableError()
        return identity if identity == IDENTITY else None


class MockBrowserVerifier(BrowserSessionVerifier):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        self.calls += 1
        return IDENTITY if credential == COOKIE else None


class GrantScenario:
    """Use production authentication and grant services with controlled provider responses."""

    def __init__(self, settings: DatabaseSettings) -> None:
        # Keep TestClient's connections separate from the async fixture's pool.
        api_database = Database(settings)
        reader = PostgresHumanIdentityLinkReader(api_database)
        recovery_block_reader = PostgresIdentityRecoveryBlockReader(api_database)
        self.token = MockTokenVerifier()
        self.identity = MockIdentityVerifier()
        self.browser = MockBrowserVerifier()

        authenticate = HumanSessionDependency(
            HumanSessionAuthenticationService(
                self.browser, reader, recovery_block_reader=recovery_block_reader
            ),
            CSRFProtectionDependency((HttpUrl(TRUSTED_ORIGIN),)),
            access_token_authenticator=HumanAccessTokenAuthenticationService(
                self.token,
                self.identity,
                reader,
                recovery_block_reader=recovery_block_reader,
            ),
        )
        fingerprints = ProjectGrantChangeFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        )

        self.application = FastAPI(
            lifespan=partial(application_lifespan, ApplicationResources(database=api_database))
        )
        register_error_handlers(self.application)
        configure_problem_openapi(self.application)
        self.application.include_router(create_session_router(authenticate))
        self.application.include_router(
            create_project_grant_router(
                authenticate, partial(open_project_grant_change, api_database, fingerprints)
            )
        )
        self.application.add_middleware(RequestContextMiddleware)


@pytest_asyncio.fixture
async def grant_seed(database: Database) -> GrantSeedDTO:
    """Admit Alice locally, let her delegate the action, and add Bob to the same project."""
    recipient_id = PrincipalId(uuid4())
    action_id = ActionId("create-access-groups")

    async with database.session() as session, session.begin():
        project = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add_all(
            [
                HumanIdentityLinkRow(
                    authority=IDENTITY.authority.value,
                    subject=IDENTITY.subject.value,
                    organization_id=project.organization_id.value,
                    principal_id=project.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                PrincipalRow(
                    id=recipient_id.value,
                    organization_id=project.organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name="Bob",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=project.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=project.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=project.project_id.value,
                    recipient_principal_id=project.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    return GrantSeedDTO(
        organization_id=project.organization_id,
        project_id=project.project_id,
        actor_id=project.principal_id,
        recipient_id=recipient_id,
        action_id=action_id,
    )


def _command(seed: GrantSeedDTO, *, expected_access_revision: int = 0) -> dict[str, str | int]:
    return {
        "recipientPrincipalId": str(seed.recipient_id.value),
        "actionId": seed.action_id.value,
        "expectedAccessRevision": expected_access_revision,
    }


def _bearer_headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN.value}",
        "Idempotency-Key": key,
    }


async def _read_state(database: Database, seed: GrantSeedDTO) -> GrantStateDTO:
    """Read all project grants and the project's audit, reservation, and revision state."""
    async with database.session() as session:
        grant_rows = (
            (
                await session.execute(
                    select(
                        ProjectActionGrantRow.recipient_principal_id,
                        ProjectActionGrantRow.action,
                        ProjectActionGrantRow.can_grant,
                    )
                    .where(ProjectActionGrantRow.project_id == seed.project_id.value)
                    .order_by(
                        ProjectActionGrantRow.recipient_principal_id,
                        ProjectActionGrantRow.action,
                    )
                )
            )
            .tuples()
            .all()
        )
        project_grants = tuple(
            ProjectGrantStateDTO(
                recipient_id=PrincipalId(recipient_id),
                action_id=ActionId(action),
                can_grant=can_grant,
            )
            for recipient_id, action, can_grant in grant_rows
        )
        audit_ids = (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.project_id == seed.project_id.value
                )
            )
        ).all()
        operation_ids = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id)
                .where(IdempotencyReservationRow.project_id == seed.project_id.value)
                .order_by(IdempotencyReservationRow.operation_id)
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.project_id.value)
        )

    assert revision is not None
    return GrantStateDTO(
        project_grants=project_grants,
        audit_count=len(audit_ids),
        operation_ids=tuple(OperationId(value) for value in operation_ids),
        access_revision=revision,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("credential_kind", ["bearer", "cookie"])
async def test_authorized_human_can_save_a_project_grant(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
    credential_kind: Literal["bearer", "cookie"],
) -> None:
    """Both login paths save the same grant - bearer writes need no cookie or CSRF headers."""
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        if credential_kind == "bearer":
            headers = _bearer_headers("grant-bob-success")
        else:
            client.cookies.set("ory_kratos_session", COOKIE.value)
            headers = {
                "Idempotency-Key": "grant-bob-success",
                "Origin": TRUSTED_ORIGIN,
                "X-Inframeld-CSRF": "1",
            }

        response = client.post(path, headers=headers, json=_command(grant_seed))

    assert response.status_code == 201, response.text
    assert response.json()["recipientPrincipalId"] == str(grant_seed.recipient_id.value)
    assert response.json()["actionId"] == grant_seed.action_id.value

    state = await _read_state(database, grant_seed)
    assert (
        ProjectGrantStateDTO(
            recipient_id=grant_seed.recipient_id,
            action_id=grant_seed.action_id,
            can_grant=False,
        )
        in state.project_grants
    )
    assert len(state.project_grants) == 2
    assert state.audit_count == 1
    assert tuple(operation.value for operation in state.operation_ids) == (
        response.json()["operationId"],
    )
    assert state.access_revision == 1
    assert scenario.token.calls == (1 if credential_kind == "bearer" else 0)
    assert scenario.identity.calls == (1 if credential_kind == "bearer" else 0)
    assert scenario.browser.calls == (1 if credential_kind == "cookie" else 0)


@pytest.mark.asyncio
async def test_valid_bearer_without_grant_authority_cannot_write(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
) -> None:
    """An authenticated human with use-only permission cannot delegate that permission."""
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == grant_seed.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == grant_seed.actor_id.value,
                ProjectActionGrantRow.action == grant_seed.action_id.value,
            )
            .values(can_grant=False)
        )

    before = await _read_state(database, grant_seed)
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        response = client.post(
            path,
            headers=_bearer_headers("grant-bob-no-authority"),
            json=_command(grant_seed),
        )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"
    assert scenario.token.calls == 1
    assert scenario.identity.calls == 1
    assert scenario.browser.calls == 0
    assert await _read_state(database, grant_seed) == before


@pytest.mark.asyncio
async def test_revoked_authority_denies_both_replay_and_new_request(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
) -> None:
    """Removing current authority blocks new writes and disclosure of a saved success."""
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"
    headers = _bearer_headers("grant-bob-original")
    command = _command(grant_seed)

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = client.post(path, headers=headers, json=command)
        assert first.status_code == 201, first.text

        # Establish the post-revocation state directly for this request-level test.
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == grant_seed.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == grant_seed.actor_id.value,
                    ProjectActionGrantRow.action == grant_seed.action_id.value,
                )
            )

        # Compare requests against the state after the intentional revocation.
        saved_state = await _read_state(database, grant_seed)
        replay = client.post(path, headers=headers, json=command)
        fresh = client.post(
            path,
            headers=_bearer_headers("grant-bob-after-revocation"),
            json=_command(grant_seed, expected_access_revision=1),
        )

    for response in (replay, fresh):
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "access_denied"
        assert "operationId" not in response.json()

    assert scenario.token.calls == 3
    assert scenario.identity.calls == 3
    assert scenario.browser.calls == 0
    assert await _read_state(database, grant_seed) == saved_state


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["hydra", "kratos"])
async def test_provider_outage_stops_a_write_after_successful_authentication(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
    provider: Literal["hydra", "kratos"],
) -> None:
    """A prior session check cannot authorize a write when either provider is now unavailable."""
    before = await _read_state(database, grant_seed)
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        first = client.get("/v1/session", headers={"Authorization": f"Bearer {TOKEN.value}"})
        assert first.status_code == 200, first.text
        assert first.json() == {"principalId": str(grant_seed.actor_id.value)}

        if provider == "hydra":
            scenario.token.unavailable = True
        else:
            scenario.identity.unavailable = True

        response = client.post(
            path,
            headers=_bearer_headers("grant-bob-provider-outage"),
            json=_command(grant_seed),
        )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "dependency_unavailable"
    assert scenario.token.calls == 2
    assert scenario.identity.calls == (1 if provider == "hydra" else 2)
    assert scenario.browser.calls == 0
    assert await _read_state(database, grant_seed) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "csrf_headers",
    [
        pytest.param({"Origin": TRUSTED_ORIGIN}, id="missing-marker"),
        pytest.param({"X-Inframeld-CSRF": "1"}, id="missing-origin"),
        pytest.param(
            {"Origin": "http://untrusted.test", "X-Inframeld-CSRF": "1"},
            id="untrusted-origin",
        ),
    ],
)
async def test_cookie_write_requires_csrf_protection(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
    csrf_headers: dict[str, str],
) -> None:
    """An eligible browser caller cannot change grants without both required CSRF checks."""
    before = await _read_state(database, grant_seed)
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        client.cookies.set("ory_kratos_session", COOKIE.value)
        response = client.post(
            path,
            headers={"Idempotency-Key": "grant-bob-csrf"} | csrf_headers,
            json=_command(grant_seed),
        )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"
    assert scenario.token.calls == 0
    assert scenario.identity.calls == 0
    assert scenario.browser.calls == 1
    assert await _read_state(database, grant_seed) == before


@pytest.mark.asyncio
async def test_competing_credentials_cannot_change_grants(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    grant_seed: GrantSeedDTO,
) -> None:
    """Ambiguous authentication is rejected before provider verification or durable writes."""
    before = await _read_state(database, grant_seed)
    scenario = GrantScenario(temporary_postgres_settings)
    path = f"/v1/projects/{grant_seed.project_id.value}/grants"

    with TestClient(scenario.application, raise_server_exceptions=False) as client:
        client.cookies.set("ory_kratos_session", COOKIE.value)
        response = client.post(
            path,
            headers=_bearer_headers("grant-bob-competing"),
            json=_command(grant_seed),
        )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_authentication_request"
    assert scenario.token.calls == 0
    assert scenario.identity.calls == 0
    assert scenario.browser.calls == 0
    assert await _read_state(database, grant_seed) == before
