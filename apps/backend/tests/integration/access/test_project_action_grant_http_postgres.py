"""Use the registered own-access and full grant HTTP contracts over real persistence."""

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import func, select
from tests.support.project_action_grant_postgres_scenarios import seed_project_grant_recipients

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_own_revision_full_grant_read_remove_and_original_recovery_over_registered_http(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_grant_recipients(database)
    browser = AsyncMock(return_value=seed.actor.binding.identity)
    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test"),
                authority=seed.actor.binding.identity.authority,
            ),
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )
    project = seed.project.project_id.value
    route = f"/v1/projects/{project}/grants/{seed.bob_id.value}/inspect-budget"
    with patch.object(KratosBrowserSessionVerifier, "verify", browser):
        application = create_app(settings)
        async with (
            application.router.lifespan_context(application),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=application),
                base_url="https://api.test",
                cookies={"ory_kratos_session": "controlled-alice"},
            ) as client,
        ):
            own = await client.get(f"/v1/projects/{project}/my-access")
            assert own.status_code == 200 and own.headers["cache-control"] == "no-store"
            assert own.json()["accessRevision"] == 2
            denied = await client.put(
                route,
                json={"canGrant": False, "expectedAccessRevision": 2},
                headers={"Idempotency-Key": "http-grant"},
            )
            assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
            async with database.session() as observer:
                assert (
                    await observer.get(
                        ProjectActionGrantRow, (project, seed.bob_id.value, "inspect-budget")
                    )
                    is None
                )
                assert await observer.scalar(select(ProjectRow.access_revision)) == 2
                assert (
                    await observer.scalar(
                        select(func.count()).select_from(ProjectActionGrantOperationResultRow)
                    )
                    == 0
                )
            headers = {
                "Origin": "https://account.test",
                "X-Inframeld-CSRF": "1",
                "Idempotency-Key": "http-grant",
            }
            assigned = await client.put(
                route,
                json={"canGrant": False, "expectedAccessRevision": own.json()["accessRevision"]},
                headers=headers,
            )
            assert assigned.status_code == 201 and assigned.json()["accessRevision"] == 3
            assert assigned.headers["cache-control"] == "no-store"
            listed = await client.get(
                f"/v1/projects/{project}/grants", params={"actionId": "inspect-budget"}
            )
            assert listed.status_code == 200 and any(
                row["recipientPrincipalId"] == str(seed.bob_id.value) and row["canGrant"] is False
                for row in listed.json()["items"]
            )
            browser.return_value = VerifiedHumanIdentityDTO(
                seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
            )
            bob = await client.get(f"/v1/projects/{project}/my-access")
            assert bob.status_code == 200 and bob.json()["principalId"] == str(seed.bob_id.value)
            assert bob.json()["accessRevision"] == 3 and len(bob.json()["grants"]) == 1
            forbidden_inventory = await client.get(f"/v1/projects/{project}/members")
            assert forbidden_inventory.status_code == 403
            browser.return_value = seed.actor.binding.identity
            removed = await client.delete(
                route,
                params={"expectedAccessRevision": 3},
                headers=headers | {"Idempotency-Key": "http-remove"},
            )
            assert (
                removed.status_code == 200
                and removed.json()["changed"]
                and removed.json()["accessRevision"] == 4
            )
            replay = await client.put(
                route, json={"canGrant": False, "expectedAccessRevision": 2}, headers=headers
            )
            assert replay.status_code == 201 and replay.json() == assigned.json()
            async with database.session() as observer:
                assert (
                    await observer.get(
                        ProjectActionGrantRow, (project, seed.bob_id.value, "inspect-budget")
                    )
                    is None
                )
                assert await observer.scalar(select(ProjectRow.access_revision)) == 4
