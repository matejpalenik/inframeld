"""Exercise the production read router with controlled authentication and real adapters."""

import os
from functools import partial
from typing import override
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy import delete
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.project_members_routes import (
    create_project_members_router,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.bootstrap.project_members_composition import open_project_members
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


class MockMembersHttpAuthenticator(HumanSessionAuthenticator):
    def __init__(self, access: AccessContextDTO) -> None:
        self._access = access

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        return self._access


async def test_created_project_members_read_maps_current_receipt_and_revocation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_project_members_router(
            ProductAccessDependency(
                MockMembersHttpAuthenticator(seed.access),
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                application_authenticator=MockApplicationAuthenticator(
                    AccessContextDTO(
                        PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
                    ),
                    failure=AuthenticationRequiredError(),
                ),
            ),
            partial(open_project_members, database),
        )
    )
    app.add_middleware(RequestContextMiddleware)
    path = f"/v1/projects/{created.project.project_id.value}/members"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="https://api.test",
        headers={"Cookie": "ory_kratos_session=controlled-members-session"},
    ) as client:
        response = await client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"projectId", "accessRevision", "items", "nextCursor"}
        assert body["projectId"] == str(created.project.project_id.value)
        assert body["accessRevision"] == 1 and body["nextCursor"] is None
        assert len(body["items"]) == 1
        assert body["items"][0]["principalId"] == str(seed.access.actor_principal_id.value)
        assert set(body["items"][0]) == {"principalId", "displayName", "kind"}
        assert response.headers["cache-control"] == "no-store"
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == created.project.project_id.value,
                    ProjectActionGrantRow.action == "manage-project-members",
                )
            )
        denied = await client.get(path)
        assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
        assert denied.headers["cache-control"] == "no-store"
