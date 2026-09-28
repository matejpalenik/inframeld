"""Verify the project grant command through its HTTP boundary."""

import os
from datetime import datetime
from functools import partial
from typing import override
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, select
from tests.support.access_scenarios import (
    MockAccessScenarios,
    ProjectAuthorizationSeedDTO,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_grant_routes import (
    create_project_grant_router,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
    AccessAuditEventRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
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


class FixedHumanSessionAuthenticator(HumanSessionAuthenticator):
    """Map two test sessions to the same principal through the HTTP dependency."""

    def __init__(self, actor_id: PrincipalId) -> None:
        self._actor_id = actor_id

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value not in {
            "test-session",
            "rotated-session",
        }:
            raise AuthenticationRequiredError()
        return AccessContextDTO(actor_principal_id=self._actor_id)


def _test_app(database: Database, actor_id: PrincipalId) -> FastAPI:
    application = FastAPI(lifespan=partial(application_lifespan, ApplicationResources(database)))
    register_error_handlers(application)
    configure_problem_openapi(application)

    authenticate = HumanSessionDependency(
        FixedHumanSessionAuthenticator(actor_id),
        CSRFProtectionDependency((HttpUrl("http://studio.test"),)),
    )
    fingerprints = ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    application.include_router(create_project_grant_router(authenticate, database, fingerprints))
    application.add_middleware(RequestContextMiddleware)
    return application


async def _seed_grantable_project_with_bob(
    database: Database,
) -> tuple[ProjectAuthorizationSeedDTO, PrincipalId, ActionId]:
    bob_id = PrincipalId(uuid4())
    action_id = ActionId("create-access-groups")

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add(
            PrincipalRow(
                id=bob_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=bob_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    return scenario, bob_id, action_id


@pytest.mark.asyncio
async def test_grant_http_key_cannot_be_reused_for_another_recipient(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """The HTTP adapter fingerprints parsed recipients before reserving a key."""
    bob_id = PrincipalId(uuid4())
    carol_id = PrincipalId(uuid4())
    action_id = ActionId("create-access-groups")

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add_all(
            [
                PrincipalRow(
                    id=principal_id.value,
                    organization_id=scenario.organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name=name,
                )
                for principal_id, name in ((bob_id, "Bob"), (carol_id, "Carol"))
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=principal_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
                for principal_id in (bob_id, carol_id)
            ]
            + [
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                )
            ]
        )

    # A separate pool belongs to the app's TestClient event loop.
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    headers = {
        "Origin": "http://studio.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "grant-recipient-1",
    }
    bob_command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")

        first = client.post(path, headers=headers, json=bob_command)
        changed = client.post(
            path,
            headers=headers,
            json={
                **bob_command,
                "recipientPrincipalId": str(carol_id.value),
            },
        )

    assert first.status_code == 201, first.text
    assert first.json()["recipientPrincipalId"] == str(bob_id.value)
    assert first.json()["operationId"]
    assert changed.status_code == 409, changed.text
    assert changed.json()["code"] == "idempotency_key_reused"

    async with database.session() as session:
        granted_recipients = (
            await session.scalars(
                select(ProjectActionGrantRow.recipient_principal_id).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id.in_(
                        (bob_id.value, carol_id.value)
                    ),
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert granted_recipients == [bob_id.value]
    assert revision == 1


@pytest.mark.asyncio
async def test_grant_http_retry_returns_original_result_without_another_change(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """A lost response can be retried without assigning or auditing twice."""
    scenario, bob_id, action_id = await _seed_grantable_project_with_bob(database)
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    headers = {
        "Origin": "http://studio.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "grant-bob-retry-1",
    }
    command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        first = client.post(path, headers=headers, json=command)
        retry = client.post(path, headers=headers, json=command)

    assert first.status_code == 201, first.text
    assert retry.status_code == 201, retry.text
    assert retry.json() == first.json()

    async with database.session() as session:
        bob_grants = (
            await session.scalars(
                select(ProjectActionGrantRow.can_grant).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == bob_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        audit_ids = (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == bob_id.value,
                    AccessAuditEventRow.event_type == "project_action_grant_assigned",
                )
            )
        ).all()
        reservation_ids = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == "grant-bob-retry-1",
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert bob_grants == [False]
    assert len(audit_ids) == 1
    assert reservation_ids == [first.json()["operationId"]]
    assert revision == 1


@pytest.mark.asyncio
async def test_grant_http_retry_is_denied_after_actor_loses_grant_authority(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """A saved result does not bypass the actor's current permission check."""
    scenario, bob_id, action_id = await _seed_grantable_project_with_bob(database)
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    headers = {
        "Origin": "http://studio.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "grant-bob-revoked-1",
    }
    command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        first = client.post(path, headers=headers, json=command)
        assert first.status_code == 201, first.text

        # Set up the post-revocation state directly; a revocation command
        # is outside the workflow exercised by this HTTP test.
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == scenario.principal_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )

        retry = client.post(path, headers=headers, json=command)

    assert retry.status_code == 403, retry.text
    assert retry.json()["code"] == "access_denied"
    assert "operationId" not in retry.json()

    async with database.session() as session:
        bob_grants = (
            await session.scalars(
                select(ProjectActionGrantRow.can_grant).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == bob_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        audit_ids = (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == bob_id.value,
                    AccessAuditEventRow.event_type == "project_action_grant_assigned",
                )
            )
        ).all()
        reservation_ids = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == "grant-bob-revoked-1",
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert bob_grants == [False]
    assert len(audit_ids) == 1
    assert reservation_ids == [first.json()["operationId"]]
    assert revision == 1


@pytest.mark.asyncio
async def test_grant_http_retry_reports_the_original_reservation_expiry(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """A retry reports the stored deadline without extending it."""
    scenario, bob_id, action_id = await _seed_grantable_project_with_bob(database)
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    headers = {
        "Origin": "http://studio.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "grant-bob-expiry-1",
    }
    command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        first = client.post(path, headers=headers, json=command)
        retry = client.post(path, headers=headers, json=command)

    assert first.status_code == 201, first.text
    assert retry.status_code == 201, retry.text

    first_expiry = datetime.fromisoformat(str(first.json()["idempotencyExpiresAt"]))
    retry_expiry = datetime.fromisoformat(str(retry.json()["idempotencyExpiresAt"]))

    async with database.session() as session:
        stored_expiry = await session.scalar(
            select(IdempotencyReservationRow.expires_at).where(
                IdempotencyReservationRow.operation_id == first.json()["operationId"]
            )
        )

    assert stored_expiry is not None
    assert first_expiry == stored_expiry
    assert retry_expiry == stored_expiry


@pytest.mark.asyncio
async def test_grant_http_rejects_duplicate_idempotency_headers_without_writing(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """An ambiguous key cannot create a grant or reserve an operation."""
    scenario, bob_id, action_id = await _seed_grantable_project_with_bob(database)
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        response = client.post(
            path,
            headers=[
                ("Origin", "http://studio.test"),
                ("X-Inframeld-CSRF", "1"),
                ("Idempotency-Key", "grant-bob-first"),
                ("Idempotency-Key", "grant-bob-second"),
            ],
            json=command,
        )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_input"

    async with database.session() as session:
        bob_grants = (
            await session.scalars(
                select(ProjectActionGrantRow.recipient_principal_id).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == bob_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        reservation_ids = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key.in_(
                        ("grant-bob-first", "grant-bob-second")
                    ),
                )
            )
        ).all()
        audit_ids = (
            await session.scalars(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == bob_id.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert bob_grants == []
    assert reservation_ids == []
    assert audit_ids == []
    assert revision == 0


@pytest.mark.asyncio
async def test_grant_http_retry_after_session_rotation_reuses_original_operation(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Changing sessions does not change the authenticated principal's retry scope."""
    scenario, bob_id, action_id = await _seed_grantable_project_with_bob(database)
    api_database = Database(temporary_postgres_settings)
    path = f"/v1/projects/{scenario.project_id.value}/grants"
    headers = {
        "Origin": "http://studio.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "grant-bob-rotated-session-1",
    }
    command: dict[str, str | int] = {
        "recipientPrincipalId": str(bob_id.value),
        "actionId": action_id.value,
        "expectedAccessRevision": 0,
    }

    with TestClient(_test_app(api_database, scenario.principal_id)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        first = client.post(path, headers=headers, json=command)

        client.cookies.set("ory_kratos_session", "rotated-session")
        retry = client.post(path, headers=headers, json=command)

    assert first.status_code == 201, first.text
    assert retry.status_code == 201, retry.text
    assert retry.json() == first.json()

    async with database.session() as session:
        reservation_ids = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == "grant-bob-rotated-session-1",
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert reservation_ids == [first.json()["operationId"]]
    assert revision == 1
