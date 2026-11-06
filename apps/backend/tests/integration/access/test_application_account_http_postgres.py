"""Exercise protected account and key disclosures through HTTP and real PostgreSQL."""

import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx2
import pytest
from sqlalchemy import delete, update
from tests.support.application_account_scenarios import account_http_application, create_account
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
_BEARER = {"Authorization": "Bearer controlled-human"}
_COOKIE = {"Cookie": "ory_kratos_session=controlled-cookie"}
_WRITE = {
    **_COOKIE,
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "http-create",
}
_VERIFIER = b"V" * 32


async def _keys(
    database: Database, account: CreatedApplicationAccountDTO
) -> tuple[ApplicationKeyId, ...]:
    installed = await PostgresInstallationIdentityReader(database).read()
    ids = tuple(ApplicationKeyId(UUID(int=value)) for value in (10, 20, 30))
    async with database.session() as session, session.begin():
        rows: list[ApplicationKeyRow] = []
        for identifier in ids:
            row = ApplicationKeyRow(
                key_id=identifier.value,
                organization_id=account.organization_id.value,
                project_id=account.project_id.value,
                application_principal_id=account.principal_id.value,
                installation_id=installed.value,
                audience="https://api.test",
                allowed_adapters=["http", "mcp"],
                verifier=_VERIFIER,
                expires_at=datetime.now(UTC) + timedelta(days=90),
                issued_by_principal_id=account.creator_principal_id.value,
            )
            session.add(row)
            rows.append(row)
        await session.flush()
        rows[1].revoked_at = rows[1].created_at
        rows[2].created_at = datetime.now(UTC) - timedelta(days=2)
        rows[2].expires_at = datetime.now(UTC) - timedelta(days=1)
        assert _VERIFIER.decode() not in repr(rows[0])
    return ids


async def test_http_creation_is_empty_csrf_protected_and_replay_preserves_original_receipt(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    application = account_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    path = f"/v1/projects/{project.project_id.value}/application-accounts"
    body = {"name": "support-bot", "displayName": "SupportBot", "expectedAccessRevision": 1}
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="http://test"
    ) as client:
        denied = await client.post(
            path, json=body, headers=_COOKIE | {"Idempotency-Key": "missing-csrf"}
        )
        assert denied.status_code == 403
        created = await client.post(path, json=body, headers=_WRITE)
        assert created.status_code == 201
        replay = await client.post(
            path, json=body, headers=_BEARER | {"Idempotency-Key": "http-create"}
        )
        assert replay.status_code == 201 and replay.json() == created.json()
        principal = created.json()["principalId"]
        metadata = await client.get(f"{path}/{principal}", headers=_BEARER)
        resolved = await client.get(
            f"{path}/resolve", params={"name": "support-bot"}, headers=_BEARER
        )
        keys = await client.get(f"{path}/{principal}/keys", headers=_BEARER)
        inventory = await client.get(path, headers=_BEARER)
    assert metadata.status_code == resolved.status_code == keys.status_code == 200
    assert metadata.json() == resolved.json()
    assert metadata.json()["principalId"] == principal and metadata.json()["accessRevision"] == 2
    assert keys.json() == {"items": [], "nextCursor": None}
    assert inventory.status_code == 405
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (created, replay, metadata, resolved, keys)
    )


@pytest.mark.parametrize(
    "authority", ["issue-application-keys", "revoke-application-keys", "delete-application-account"]
)
async def test_safe_key_reads_need_issue_or_revoke_without_issuance_delegation(
    database: Database, authority: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    account = (await create_account(database, seed.access, project.project_id)).account
    ids = await _keys(database, account)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.application_principal_id == account.principal_id.value,
                ApplicationActionGrantRow.action != authority,
            )
        )
        await session.execute(
            update(ApplicationActionGrantRow)
            .where(ApplicationActionGrantRow.application_principal_id == account.principal_id.value)
            .values(can_grant=False)
        )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.recipient_principal_id
                == seed.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "inspect-budget",
            )
        )
        session.add(
            ProjectActionGrantRow(
                project_id=project.project_id.value,
                recipient_principal_id=account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action="inspect-budget",
                can_grant=False,
            )
        )
        group = AccessGroupRow(
            id=uuid4(), project_id=project.project_id.value, name="Private audience"
        )
        session.add(group)
        await session.flush()
        session.add(
            GroupMembershipRow(
                project_id=project.project_id.value,
                group_id=group.id,
                principal_id=account.principal_id.value,
            )
        )
    application = account_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    path = (
        f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}"
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="http://test"
    ) as client:
        metadata = await client.get(path, headers=_BEARER)
        listed = await client.get(path + "/keys", headers=_BEARER)
        one = await client.get(path + f"/keys/{ids[0].value}", headers=_BEARER)
    assert metadata.status_code == 200
    if authority == "delete-application-account":
        assert listed.status_code == one.status_code == 403
        return
    assert listed.status_code == one.status_code == 200
    assert [item["keyId"] for item in listed.json()["items"]] == [str(value.value) for value in ids]
    for item in listed.json()["items"]:
        assert set(item) == {
            "keyId",
            "applicationPrincipalId",
            "projectId",
            "prefix",
            "allowedAdapters",
            "createdAt",
            "expiresAt",
            "revokedAt",
        }
        assert item["prefix"] == "ifm_app_" and item["applicationPrincipalId"] == str(
            account.principal_id.value
        )
    assert (
        _VERIFIER.decode() not in listed.text
        and base64.b64encode(_VERIFIER).decode() not in listed.text
    )
    assert listed.json()["items"][1]["revokedAt"] is not None
    assert one.json() == listed.json()["items"][0]


async def test_uuid_key_pages_reauthorize_empty_continuations_and_bind_exact_scope(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    account = (await create_account(database, seed.access, project.project_id)).account
    ids = await _keys(database, account)
    other_project = (
        await create_project(database, seed, name="other", key="other-project")
    ).project
    other_account = (
        await create_account(database, seed.access, other_project.project_id, key="other-account")
    ).account
    application = account_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    path = f"/v1/projects/{project.project_id.value}/application-accounts/{account.principal_id.value}/keys"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="http://test"
    ) as client:
        first = await client.get(path, params={"limit": 2}, headers=_BEARER)
        assert first.status_code == 200
        cursor = first.json()["nextCursor"]
        assert cursor is not None and len(first.json()["items"]) == 2
        second = await client.get(path, params={"limit": 2, "cursor": cursor}, headers=_BEARER)
        assert second.status_code == 200 and [item["keyId"] for item in second.json()["items"]] == [
            str(ids[2].value)
        ]
        assert second.json()["nextCursor"] is None
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ApplicationKeyRow).where(ApplicationKeyRow.key_id == ids[2].value)
            )
        empty = await client.get(path, params={"cursor": cursor}, headers=_BEARER)
        assert empty.status_code == 200 and empty.json() == {"items": [], "nextCursor": None}
        mismatch = await client.get(
            f"/v1/projects/{other_project.project_id.value}/application-accounts/{other_account.principal_id.value}/keys",
            params={"cursor": cursor},
            headers=_BEARER,
        )
        assert mismatch.status_code == 422
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.application_principal_id
                    == account.principal_id.value,
                    ApplicationActionGrantRow.action != "delete-application-account",
                )
            )
        denied = await client.get(path, params={"cursor": cursor}, headers=_BEARER)
        assert denied.status_code == 403


async def test_hidden_accounts_wrong_project_and_changed_credential_do_not_disclose_metadata(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    account = (await create_account(database, seed.access, project.project_id)).account
    other = (await create_project(database, seed, name="other", key="other-project")).project
    application = account_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    base = f"/v1/projects/{project.project_id.value}/application-accounts"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="http://test"
    ) as client:
        assert (
            await client.get(
                f"/v1/projects/{other.project_id.value}/application-accounts/{account.principal_id.value}",
                headers=_BEARER,
            )
        ).status_code == 404
        assert (
            await client.get(base + "/resolve", params={"name": "support"}, headers=_BEARER)
        ).status_code == 404
        assert (
            await client.get(
                base + f"/{account.principal_id.value}/keys/{uuid4()}", headers=_BEARER
            )
        ).status_code == 404
        async with database.session() as session, session.begin():
            await session.execute(
                update(HumanCredentialVersionRow).values(
                    version=HumanCredentialVersionRow.version + 1
                )
            )
        stale = await client.get(base + f"/{account.principal_id.value}", headers=_BEARER)
        assert stale.status_code == 401
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.application_principal_id == account.principal_id.value
                )
            )
        for suffix in (
            f"/{account.principal_id.value}",
            "/resolve?name=support-bot",
            f"/{account.principal_id.value}/keys",
        ):
            assert (await client.get(base + suffix, headers=_COOKIE)).status_code == 404


async def test_concrete_creation_context_is_found_by_generic_lookup_under_current_authority(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    created = await create_account(database, seed.access, project.project_id)
    other = (await create_project(database, seed, name="other", key="other-project")).project
    installed = await PostgresInstallationIdentityReader(database).read()
    path = f"/v1/projects/{project.project_id.value}/application-accounts"
    lookup = {
        "installationId": str(installed.value),
        "organizationId": str(seed.organization_id.value),
        "projectId": str(project.project_id.value),
        "method": "POST",
        "requestedRoute": path,
        "key": "create-bot",
        "expectedAuthority": {
            "family": "project_action_use",
            "actionId": "create-application-accounts",
        },
    }
    application = account_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="http://test"
    ) as client:
        original = await client.post("/v1/operations/lookup", json=lookup, headers=_BEARER)
        assert original.status_code == 200
        assert original.json()["operationId"] == created.operation.operation_id.value
        assert original.json()["classification"] == "safe_result"
        wrong_scope = await client.post(
            "/v1/operations/lookup",
            json={**lookup, "projectId": str(other.project_id.value)},
            headers=_BEARER,
        )
        assert wrong_scope.status_code == 200 and wrong_scope.json()["outcome"] == "unresolved"
        wrong_route = await client.post(
            "/v1/operations/lookup",
            json={**lookup, "requestedRoute": "/v1/projects/{project_id}/application-accounts"},
            headers=_BEARER,
        )
        assert wrong_route.status_code == 200 and wrong_route.json()["outcome"] == "unresolved"
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.project_id.value,
                    ProjectActionGrantRow.action == "create-application-accounts",
                )
            )
        for key in ("create-bot", "missing"):
            denied = await client.post(
                "/v1/operations/lookup", json={**lookup, "key": key}, headers=_BEARER
            )
            assert denied.status_code == 403
