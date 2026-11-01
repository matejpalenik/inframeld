"""Exercise real metadata routes, scope resolution and persistence with controlled authentication."""

import os
from functools import partial
from typing import override

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy import delete, update
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_metadata_scenarios import (
    seed_another_metadata_project,
    seed_metadata_project,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_metadata_routes import (
    create_project_metadata_router,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.project_metadata_composition import (
    open_project_metadata,
    open_project_name_resolution,
)
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
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
HEADERS = {
    "Cookie": "ory_kratos_session=metadata-session",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "original",
}


class MockMetadataHttpAuthenticator(HumanSessionAuthenticator):
    def __init__(self, actor: PrincipalId) -> None:
        self._actor = actor

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "metadata-session":
            raise AuthenticationRequiredError()
        return AccessContextDTO(self._actor, MockAuthenticationEvidence.browser())


def application(database: Database, actor: PrincipalId) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    fingerprints = ProjectMetadataFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    open_metadata = partial(open_project_metadata, database, fingerprints)
    app.include_router(
        create_project_metadata_router(
            HumanSessionDependency(
                MockMetadataHttpAuthenticator(actor),
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
            ),
            open_metadata,
            open_metadata,
            partial(open_project_name_resolution, database),
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return app


@pytest.mark.asyncio
async def test_http_allocates_legacy_selector_and_recovers_original_id_after_rename(
    database: Database,
) -> None:
    legacy = " legacy\x01\nlabel " + "a" * 1000
    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
        await session.execute(
            update(ProjectRow).where(ProjectRow.id == seed.project_id.value).values(name=legacy)
        )
    app = application(database, seed.principal_id)
    url = f"/v1/projects/{seed.project_id.value}/metadata"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://api.test", headers=HEADERS
    ) as client:
        before = await client.get(url)
        assert before.status_code == 200 and before.json()["name"] is None
        assert before.json()["displayName"] == legacy
        body = {"expectedMetadataRevision": 0, "name": "support"}
        first = await client.patch(url, json=body)
        assert first.status_code == 200 and first.json()["displayName"] == legacy
        resolved = await client.get("/v1/projects/by-name/support")
        assert resolved.status_code == 200 and resolved.json()["projectId"] == str(
            seed.project_id.value
        )
        renamed = await client.patch(
            url,
            json={"expectedMetadataRevision": 1, "name": "legal", "displayName": "Legal"},
            headers={"Idempotency-Key": "rename"},
        )
        assert renamed.status_code == 200
        assert (
            await client.patch(
                url,
                json={"expectedMetadataRevision": 2, "name": "research"},
                headers={"Idempotency-Key": "rename-again"},
            )
        ).status_code == 200
        for retired in ("support", "legal"):
            stopped = await client.get(f"/v1/projects/by-name/{retired}")
            assert stopped.status_code == 404 and stopped.json()["code"] == "resource_not_found"
            assert str(seed.project_id.value) in stopped.json()["detail"]
            assert "research" in stopped.json()["detail"]
            assert "location" not in stopped.headers
        current = await client.get(url)
        assert current.json()["name"] == "research" and current.json()["projectId"] == str(
            seed.project_id.value
        )
        replay = await client.patch(url, json=body)
        assert replay.status_code == 200 and replay.json() == first.json()
        assert current.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_duplicate_labels_do_not_select_and_current_authority_guards_replay_and_visibility(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
        other = await seed_another_metadata_project(session, seed)
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id.in_((seed.project_id.value, other.project_id.value)))
            .values(name="same")
        )
    app = application(database, seed.principal_id)
    url = f"/v1/projects/{seed.project_id.value}/metadata"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://api.test", headers=HEADERS
    ) as client:
        assert (await client.get("/v1/projects/by-name/same")).status_code == 404
        body = {"expectedMetadataRevision": 0, "name": "support"}
        assert (await client.patch(url, json=body)).status_code == 200
        collision = await client.patch(
            f"/v1/projects/{other.project_id.value}/metadata",
            json={"expectedMetadataRevision": 0, "name": "support", "displayName": "Changed"},
        )
        assert collision.status_code == 409
        other_metadata = await client.get(f"/v1/projects/{other.project_id.value}/metadata")
        assert (
            other_metadata.json()["name"] is None and other_metadata.json()["displayName"] == "same"
        )
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value,
                    ProjectActionGrantRow.action == "edit-project-metadata",
                )
            )
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
                .values(access_revision=ProjectRow.access_revision + 1)
            )
        assert (await client.patch(url, json=body)).status_code == 403
        assert (await client.get(url)).status_code == 200
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == seed.project_id.value
                )
            )
        assert (await client.get(url)).status_code == 404
        assert (await client.get("/v1/projects/by-name/support")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "restriction", ["membership", "inactive-project", "suspended-human", "other-organization"]
)
async def test_retired_name_guidance_never_discloses_identity_after_visibility_loss(
    database: Database,
    restriction: str,
) -> None:
    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.domain.enums.project_status import ProjectStatus
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow

    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
    app = application(database, seed.principal_id)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://api.test", headers=HEADERS
    ) as client:
        url = f"/v1/projects/{seed.project_id.value}/metadata"
        assert (
            await client.patch(url, json={"expectedMetadataRevision": 0, "name": "former"})
        ).status_code == 200
        assert (
            await client.patch(
                url,
                json={"expectedMetadataRevision": 1, "name": "current-secret"},
                headers={"Idempotency-Key": "rename"},
            )
        ).status_code == 200
    actor = seed.principal_id
    async with database.session() as session, session.begin():
        if restriction == "membership":
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == seed.project_id.value
                )
            )
        elif restriction == "inactive-project":
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
        elif restriction == "suspended-human":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == actor.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            actor = (await seed_metadata_project(session)).principal_id
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application(database, actor)),
        base_url="https://api.test",
        headers=HEADERS,
    ) as client:
        denied = await client.get("/v1/projects/by-name/former")
        assert denied.status_code in (403, 404)
        assert str(seed.project_id.value) not in denied.text
        assert "current-secret" not in denied.text
        assert "location" not in denied.headers
