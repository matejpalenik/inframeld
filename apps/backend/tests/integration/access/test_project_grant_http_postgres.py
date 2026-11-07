"""Observe retained POST metadata after its live mutation interface is removed."""

import os
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import func, select, update
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.historical_project_grant_scenarios import (
    RetainedProjectGrantPostDTO,
    seed_retained_project_grant_post,
)
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.project_action_grant_postgres_scenarios import change_project_grant

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.project_action_grant_routes import (
    create_project_action_grant_router,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.bootstrap.project_action_grants_composition import open_project_action_grants
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
HEADERS = {"Origin": "http://account.test", "X-Inframeld-CSRF": "1"}


class FixedHumanSessionAuthenticator(HumanSessionAuthenticator):
    def __init__(self, access: AccessContextDTO) -> None:
        self._access = access

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value not in {"test-session", "rotated-session"}:
            raise AuthenticationRequiredError()
        return self._access


def _test_app(database: Database, access: AccessContextDTO) -> FastAPI:
    app = FastAPI(lifespan=partial(application_lifespan, ApplicationResources(database)))
    register_error_handlers(app)
    configure_problem_openapi(app)
    authenticate = ProductAccessDependency(
        FixedHumanSessionAuthenticator(access),
        CSRFProtectionDependency((HttpUrl("http://account.test"),)),
        application_authenticator=MockApplicationAuthenticator(
            AccessContextDTO(
                PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
            ),
            failure=AuthenticationRequiredError(),
        ),
    )
    app.include_router(
        create_project_action_grant_router(
            authenticate, partial(open_project_action_grants, database)
        )
    )
    app.include_router(
        create_original_operation_lookup_router(
            authenticate, partial(open_original_operation_lookup, database)
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return app


def _lookup_body(retained: RetainedProjectGrantPostDTO) -> dict[str, object]:
    query = retained.query
    assert query.project_id is not None
    return {
        "installationId": str(query.installation_id.value),
        "organizationId": str(query.organization_id.value),
        "projectId": str(query.project_id.value),
        "method": query.method.value,
        "requestedRoute": query.requested_route,
        "key": query.key.value,
        "expectedAuthority": {"family": "project_grant_read", "actionId": "create-access-groups"},
    }


async def _effects(database: Database) -> tuple[int, int, int]:
    async with database.session() as session:
        return (
            (await session.scalar(select(func.count()).select_from(ProjectActionGrantRow))) or 0,
            (await session.scalar(select(func.count()).select_from(AccessAuditEventRow))) or 0,
            (await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)))
            or 0,
        )


async def test_retired_post_old_body_is_405_without_mutation_or_history_change(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    retained = await seed_retained_project_grant_post(database)
    before = await _effects(database)
    with TestClient(
        _test_app(Database(temporary_postgres_settings), retained.seed.actor.access)
    ) as client:
        response = client.post(
            f"/v1/projects/{retained.seed.project.project_id.value}/grants",
            headers=HEADERS | {"Idempotency-Key": retained.query.key.value},
            json={
                "recipientPrincipalId": str(retained.seed.bob_id.value),
                "actionId": "create-access-groups",
                "canGrant": False,
                "expectedAccessRevision": 2,
            },
        )
    assert response.status_code == 405 and response.headers["cache-control"] == "no-store"
    assert await _effects(database) == before


async def test_retained_post_acknowledgment_is_read_only_after_recipient_and_revision_change(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    retained = await seed_retained_project_grant_post(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == retained.seed.bob_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == retained.seed.project.project_id.value)
            .values(access_revision=3)
        )
    before = await _effects(database)
    with TestClient(
        _test_app(Database(temporary_postgres_settings), retained.seed.actor.access)
    ) as client:
        for cookie in ("test-session", "rotated-session", "test-session"):
            client.cookies.set("ory_kratos_session", cookie)
            response = client.post(
                "/v1/operations/lookup", json=_lookup_body(retained), headers=HEADERS
            )
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert response.json() == {
                "outcome": "completed_synchronous",
                "operationId": retained.operation_id.value,
                "classification": "safe_result",
                "idempotencyExpiresAt": retained.expires_at.isoformat().replace("+00:00", "Z"),
            }
            assert "location" not in response.headers
    assert await _effects(database) == before
    async with database.session() as session:
        row = await session.get(IdempotencyReservationRow, retained.operation_id.value)
        assert (
            row is not None
            and row.request_fingerprint == retained.fingerprint
            and row.expires_at == retained.expires_at
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == retained.seed.project.project_id.value
                )
            )
            == 3
        )


@pytest.mark.parametrize("expired", [False, True])
async def test_retained_post_missing_or_expired_identity_is_uniformly_unresolved(
    database: Database, temporary_postgres_settings: DatabaseSettings, expired: bool
) -> None:
    retained = await seed_retained_project_grant_post(database)
    body = _lookup_body(retained)
    expiry = retained.expires_at
    if expired:
        expiry = datetime.now(UTC) - timedelta(hours=1)
        async with database.session() as session, session.begin():
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == retained.operation_id.value)
                .values(expires_at=expiry)
            )
    else:
        body["key"] = "unknown-original"
    before = await _effects(database)
    with TestClient(
        _test_app(Database(temporary_postgres_settings), retained.seed.actor.access)
    ) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        response = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
    assert response.status_code == 200 and response.json() == {"outcome": "unresolved"}
    assert response.headers["cache-control"] == "no-store" and await _effects(database) == before
    async with database.session() as session:
        assert (
            await session.scalar(
                select(IdempotencyReservationRow.expires_at).where(
                    IdempotencyReservationRow.operation_id == retained.operation_id.value
                )
            )
            == expiry
        )


async def test_retained_post_lookup_preserves_current_delegation_before_known_or_unknown_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    retained = await seed_retained_project_grant_post(database)
    seed = retained.seed
    await change_project_grant(
        database,
        seed,
        revision=2,
        key="historical-http-delegate-bob",
        action_id=ActionId("create-access-groups"),
        can_grant=True,
    )
    bob = AccessContextDTO(
        actor_principal_id=seed.bob_id,
        authentication_evidence=MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                authority=seed.actor.binding.identity.authority,
                subject=IdentitySubject(str(UUID(int=200))),
            )
        ),
    )
    await change_project_grant(
        database,
        seed,
        revision=3,
        key="historical-http-downgrade-alice",
        action_id=ActionId("create-access-groups"),
        recipient=seed.actor.access.actor_principal_id,
        can_grant=False,
        access=bob,
    )
    before = await _effects(database)
    with TestClient(_test_app(Database(temporary_postgres_settings), seed.actor.access)) as client:
        client.cookies.set("ory_kratos_session", "test-session")
        for key in (retained.query.key.value, "unknown-original"):
            response = client.post(
                "/v1/operations/lookup", json=_lookup_body(retained) | {"key": key}, headers=HEADERS
            )
            assert response.status_code == 403 and response.json()["code"] == "access_denied"
        weaker = _lookup_body(retained) | {
            "expectedAuthority": {
                "family": "project_action_use",
                "actionId": "create-access-groups",
            }
        }
        assert client.post("/v1/operations/lookup", json=weaker, headers=HEADERS).status_code == 422
    assert await _effects(database) == before
