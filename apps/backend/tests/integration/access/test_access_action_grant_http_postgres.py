"""Run new grant HTTP families through actual scope, persistence, lookup and reads."""

import os
from unittest.mock import AsyncMock, patch

import httpx2
import pytest
from pydantic import HttpUrl
from tests.support.access_group_scenarios import create_group
from tests.support.application_account_scenarios import create_account
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

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


async def _review(client: httpx2.AsyncClient, path: str) -> int:
    response = await client.get(path)
    assert response.status_code == 200
    value: object = response.json()["accessRevision"]
    assert type(value) is int
    return value


@pytest.mark.parametrize("kind", ["organization", "access-group", "application-account"])
async def test_registered_exact_grant_change_read_directory_and_original_recovery(
    database: Database, temporary_postgres_settings: DatabaseSettings, kind: str
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-http-grant-recipient")
    group = (
        await create_group(
            database,
            seed.actor.access,
            seed.project.project_id,
            revision=2,
            name="http-knowledge",
            key="http-group",
        )
    ).group
    account = (
        await create_account(
            database,
            seed.actor.access,
            seed.project.project_id,
            revision=3,
            name="http-support-bot",
            key="http-account",
        )
    ).account
    project = str(seed.project.project_id.value)
    organization = str(seed.actor.organization_id.value)
    recipient = str(seed.bob_id.value)
    if kind == "organization":
        base = f"/v1/organizations/{organization}"
        action, family, own = (
            "create-projects",
            "organization_grant_read",
            "/v1/my-organization-access",
        )
        target = {"organizationId": organization}
        directory_kind, directory_id, directory_action = "project", project, "create-access-groups"
    elif kind == "access-group":
        base = f"/v1/projects/{project}/access-groups/{group.group_id.value}"
        action, family, own = (
            "add-documents",
            "access_group_grant_read",
            f"/v1/projects/{project}/my-access",
        )
        target = {"projectId": project, "accessGroupId": str(group.group_id.value)}
        directory_kind, directory_id, directory_action = kind, str(group.group_id.value), action
    else:
        base = f"/v1/projects/{project}/application-accounts/{account.principal_id.value}"
        action, family, own = (
            "issue-application-keys",
            "application_account_grant_read",
            f"/v1/projects/{project}/my-access",
        )
        target = {"projectId": project, "applicationPrincipalId": str(account.principal_id.value)}
        directory_kind, directory_id, directory_action = (
            kind,
            str(account.principal_id.value),
            action,
        )
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
    route = f"{base}/grants/{recipient}/{action}"
    original_key = "http-exact-original"
    headers = {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}
    with patch.object(
        KratosBrowserSessionVerifier, "verify", AsyncMock(return_value=seed.actor.binding.identity)
    ):
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="https://api.test",
                cookies={"ory_kratos_session": "controlled-human"},
            ) as client,
        ):
            original_body = {"canGrant": True, "expectedAccessRevision": await _review(client, own)}
            original = await client.put(
                route, json=original_body, headers=headers | {"Idempotency-Key": original_key}
            )
            assert original.status_code == 201 and original.headers["cache-control"] == "no-store"
            receipt = original.json()
            assert target.items() <= receipt.items()
            assert receipt["canGrant"] is True and receipt["changed"] is True
            lookup_body = {
                "installationId": str(seed.actor.binding.installation_id.value),
                "organizationId": organization,
                "projectId": None if kind == "organization" else project,
                "method": "PUT",
                "requestedRoute": route,
                "key": original_key,
                "expectedAuthority": {"family": family, "actionId": action},
            }
            if kind == "access-group":
                denied = await client.post(
                    "/v1/operations/lookup", json=lookup_body, headers=headers
                )
                assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
                self_route = f"{base}/grants/{seed.actor.access.actor_principal_id.value}/{action}"
                delegated = await client.put(
                    self_route,
                    json={"canGrant": True, "expectedAccessRevision": await _review(client, own)},
                    headers=headers | {"Idempotency-Key": "http-manager-exact-delegation"},
                )
                assert delegated.status_code == 201
            observed = await client.post("/v1/operations/lookup", json=lookup_body, headers=headers)
            assert (
                observed.status_code == 200
                and observed.json()["operationId"] == receipt["operationId"]
            )
            assert set(observed.json()) == {
                "outcome",
                "operationId",
                "classification",
                "idempotencyExpiresAt",
            }
            listed = await client.get(base + "/grants", params={"actionId": action, "limit": 100})
            assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
            assert {
                **target,
                "recipientPrincipalId": recipient,
                "actionId": action,
                "canGrant": True,
            } in listed.json()["items"]
            for level, expected_changed in ((True, False), (False, True)):
                changed = await client.put(
                    route,
                    json={"canGrant": level, "expectedAccessRevision": await _review(client, own)},
                    headers=headers | {"Idempotency-Key": "http-level-" + str(level)},
                )
                assert (
                    changed.status_code == 200
                    and changed.json()["canGrant"] is level
                    and changed.json()["changed"] is expected_changed
                )
            removed = await client.delete(
                route,
                params={"expectedAccessRevision": await _review(client, own)},
                headers=headers | {"Idempotency-Key": "http-remove"},
            )
            assert (
                removed.status_code == 200
                and removed.json()["removed"] is True
                and removed.json()["changed"] is True
            )
            replay = await client.put(
                route, json=original_body, headers=headers | {"Idempotency-Key": original_key}
            )
            assert replay.status_code == 201 and replay.json() == receipt
            after = await client.get(base + "/grants", params={"actionId": action, "limit": 100})
            assert after.status_code == 200 and all(
                item["recipientPrincipalId"] != recipient for item in after.json()["items"]
            )
            choices = await client.get(
                f"/v1/projects/{project}/grant-recipients",
                params={
                    "targetKind": directory_kind,
                    "targetId": directory_id,
                    "actionId": directory_action,
                    "limit": 100,
                },
            )
            assert choices.status_code == 200 and choices.headers["cache-control"] == "no-store"
            assert all(
                set(item) == {"principalId", "displayName", "kind"}
                for item in choices.json()["items"]
            )
            assert {recipient, str(seed.actor.access.actor_principal_id.value)} <= {
                item["principalId"] for item in choices.json()["items"]
            }
