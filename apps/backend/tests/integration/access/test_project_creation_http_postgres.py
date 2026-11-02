"""Exercise creation HTTP contracts with controlled authentication and actual persistence."""

import os
from functools import partial
from typing import override
from uuid import uuid4

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy import delete, func, select
from tests.support.project_creation_scenarios import (
    INITIAL_ACTIONS,
    creation_fingerprints,
    seed_project_creator,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.organization_access_routes import (
    create_organization_access_router,
)
from inframeld_backend.access.http.routes.project_creation_routes import (
    create_project_creation_router,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.organization_access_composition import open_my_organization_access
from inframeld_backend.bootstrap.project_creation_composition import open_project_creation
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
HEADERS = {
    "Cookie": "ory_kratos_session=creation-session",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "original",
}


class MockCreationHttpAuthenticator(HumanSessionAuthenticator):
    def __init__(self, access: AccessContextDTO) -> None:
        self._access = access

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "creation-session":
            raise AuthenticationRequiredError()
        return self._access


def _application(database: Database, access: AccessContextDTO) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    authenticate = HumanSessionDependency(
        MockCreationHttpAuthenticator(access),
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
    )
    app.include_router(
        create_organization_access_router(
            authenticate, partial(open_my_organization_access, database)
        )
    )
    app.include_router(
        create_project_creation_router(
            authenticate, partial(open_project_creation, database, creation_fingerprints())
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return app


async def test_http_creation_returns_exact_targets_and_original_receipt_before_current_revocation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    app = _application(database, seed.access)
    body = {
        "organizationId": str(seed.organization_id.value),
        "expectedAccessRevision": 1,
        "name": "support",
        "displayName": "Support",
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://api.test", headers=HEADERS
    ) as client:
        own = await client.get("/v1/my-organization-access")
        assert own.status_code == 200
        assert own.json()["organizationId"] == str(seed.organization_id.value)
        assert own.json()["principalId"] == str(seed.access.actor_principal_id.value)
        assert own.json()["accessRevision"] == 1
        first = await client.post("/v1/projects", json=body)
        assert first.status_code == 201
        result = first.json()
        assert set(result) == {
            "operationId",
            "idempotencyExpiresAt",
            "organizationId",
            "projectId",
            "name",
            "displayName",
            "accessRevision",
            "metadataRevision",
            "initialGrants",
        }
        assert result["organizationId"] == str(seed.organization_id.value)
        assert (
            result["name"],
            result["displayName"],
            result["accessRevision"],
            result["metadataRevision"],
        ) == ("support", "Support", 1, 0)
        assert result["initialGrants"] == [
            {
                "target": {"kind": "project", "projectId": result["projectId"]},
                "actionId": action,
                "canGrant": True,
            }
            for action in INITIAL_ACTIONS
        ]
        replay = await client.post("/v1/projects", json=body)
        assert replay.status_code == 201 and replay.json() == result
        assert (
            first.headers["cache-control"]
            == replay.headers["cache-control"]
            == own.headers["cache-control"]
            == "no-store"
        )
        async with database.session() as session, session.begin():
            await session.execute(delete(OrganizationActionGrantRow))
        empty = await client.get("/v1/my-organization-access")
        assert empty.status_code == 200 and empty.json()["grants"] == []
        denied = await client.post("/v1/projects", json=body)
        assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
        assert denied.headers["cache-control"] == "no-store"
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 1
        )


@pytest.mark.parametrize(
    "case, status",
    [
        ("unknown-field", 422),
        ("boolean-revision", 422),
        ("invalid-name", 422),
        ("invalid-label", 422),
        ("duplicate-json", 422),
        ("body-limit", 413),
        ("media-type", 415),
        ("missing-csrf", 403),
        ("duplicate-key", 422),
        ("foreign-org", 404),
    ],
)
async def test_http_rejection_leaves_no_project_or_retry_reservation(
    database: Database, case: str, status: int
) -> None:
    seed = await seed_project_creator(database)
    body: dict[str, object] = {
        "organizationId": str(seed.organization_id.value),
        "expectedAccessRevision": 1,
        "name": "support",
        "displayName": "Support",
    }
    headers = dict(HEADERS)
    if case == "unknown-field":
        body["canGrant"] = True
    elif case == "boolean-revision":
        body["expectedAccessRevision"] = True
    elif case == "invalid-name":
        body["name"] = "Support"
    elif case == "invalid-label":
        body["displayName"] = "bad\nlabel"
    elif case == "foreign-org":
        body["organizationId"] = str(uuid4())
    elif case == "missing-csrf":
        del headers["X-Inframeld-CSRF"]
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_application(database, seed.access)),
        base_url="https://api.test",
    ) as client:
        if case == "duplicate-json":
            response = await client.post(
                "/v1/projects",
                content=b'{"name":"one","name":"two"}',
                headers={**headers, "Content-Type": "application/json"},
            )
        elif case == "body-limit":
            response = await client.post(
                "/v1/projects",
                content=b" " * 32769,
                headers={**headers, "Content-Type": "application/json"},
            )
        elif case == "media-type":
            response = await client.post(
                "/v1/projects", content=b"{}", headers={**headers, "Content-Type": "text/plain"}
            )
        elif case == "duplicate-key":
            response = await client.post(
                "/v1/projects", json=body, headers=[*headers.items(), ("Idempotency-Key", "second")]
            )
        else:
            response = await client.post("/v1/projects", json=body, headers=headers)
    assert response.status_code == status
    if case in ("duplicate-json", "duplicate-key"):
        assert response.json()["code"] == "invalid_input"
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
