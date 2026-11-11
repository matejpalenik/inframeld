"""Exercise group HTTP mutations and retained recovery through real PostgreSQL owners."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx2
import pytest
from sqlalchemy import delete, func, select, update
from tests.support.access_group_scenarios import create_group, delete_group, group_http_application
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

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
    "Idempotency-Key": "http-create-group",
}


async def test_http_creation_relationships_and_original_replay_preserve_exact_outcomes(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-bob")
    app = group_http_application(
        database,
        seed.actor.access,
        AccessContextDTO(seed.actor.access.actor_principal_id, seed.actor.binding),
    )
    root = f"/v1/projects/{seed.project.project_id.value}/access-groups"
    body = {
        "name": "support-knowledge",
        "displayName": "SupportKnowledge",
        "expectedAccessRevision": 2,
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(root, json=body, headers=_COOKIE | {"Idempotency-Key": "no-csrf"})
        ).status_code == 403
        created = await client.post(root, json=body, headers=_WRITE)
        assert created.status_code == 201
        receipt = created.json()
        group = receipt["accessGroupId"]
        assert (
            receipt["creatorPrincipalId"] == str(seed.actor.access.actor_principal_id.value)
            and receipt["accessRevision"] == 3
        )
        replay = await client.post(
            root, json=body, headers=_BEARER | {"Idempotency-Key": "http-create-group"}
        )
        assert replay.status_code == 201 and replay.json() == receipt
        conflict = await client.post(root, json={**body, "displayName": "Changed"}, headers=_WRITE)
        assert conflict.status_code == 409
        metadata = await client.get(f"{root}/{group}", headers=_BEARER)
        resolved = await client.get(
            root + "/resolve", params={"name": "support-knowledge"}, headers=_BEARER
        )
        assert (
            metadata.status_code == resolved.status_code == 200
            and metadata.json() == resolved.json()
        )
        member = f"{root}/{group}/members/{seed.bob_id.value}"
        manager = f"{root}/{group}/managers/{seed.bob_id.value}"
        added = await client.put(
            member,
            json={"expectedAccessRevision": 3},
            headers=_BEARER | {"Idempotency-Key": "join-group"},
        )
        assert (
            added.status_code == 201
            and added.json()["member"] is True
            and added.json()["accessRevision"] == 4
        )
        noop = await client.put(
            member,
            json={"expectedAccessRevision": 4},
            headers=_BEARER | {"Idempotency-Key": "already-group"},
        )
        assert (
            noop.status_code == 200
            and noop.json()["changed"] is False
            and noop.json()["accessRevision"] == 4
        )
        appointed = await client.put(
            manager,
            json={"expectedAccessRevision": 4},
            headers=_BEARER | {"Idempotency-Key": "manage-group"},
        )
        assert appointed.status_code == 201 and appointed.json()["manager"] is True
        demoted = await client.delete(
            manager,
            params={"expectedAccessRevision": 5},
            headers=_BEARER | {"Idempotency-Key": "demote-group"},
        )
        assert demoted.status_code == 200 and demoted.json()["accessRevision"] == 6
        members = await client.get(f"{root}/{group}/members", headers=_BEARER)
        assert {item["principalId"] for item in members.json()["items"]} == {
            str(seed.bob_id.value),
            str(seed.actor.access.actor_principal_id.value),
        }
        removed = await client.delete(
            member,
            params={"expectedAccessRevision": 6},
            headers=_BEARER | {"Idempotency-Key": "remove-group-member"},
        )
        assert removed.status_code == 200 and removed.json()["removed"] is True
        original = await client.put(
            manager,
            json={"expectedAccessRevision": 4},
            headers=_BEARER | {"Idempotency-Key": "manage-group"},
        )
        assert original.status_code == 201 and original.json() == appointed.json()
        page = await client.get(f"{root}/{group}/managers", headers=_BEARER)
        assert [item["principalId"] for item in page.json()["items"]] == [
            str(seed.actor.access.actor_principal_id.value)
        ]
        assert all(
            response.headers["cache-control"] == "no-store"
            for response in (
                created,
                replay,
                metadata,
                resolved,
                added,
                noop,
                appointed,
                demoted,
                removed,
                original,
                page,
            )
        )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(GroupActionGrantRow)) == 0


@pytest.mark.parametrize("ordinary_history", ["expired", "removed"])
async def test_lost_delete_response_recovers_content_free_status_after_ordinary_history_is_gone(
    database: Database, ordinary_history: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    group = (await create_group(database, seed.access, project.project_id)).group
    app = group_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    installed = await PostgresInstallationIdentityReader(database).read()
    path = f"/v1/projects/{project.project_id.value}/access-groups/{group.group_id.value}"
    query = {
        "installationId": str(installed.value),
        "organizationId": str(seed.organization_id.value),
        "projectId": str(project.project_id.value),
        "method": "DELETE",
        "requestedRoute": path,
        "key": "lost-delete-response",
        "expectedAuthority": {"family": "access_group_deletion", "actionId": "delete-access-group"},
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        deleted = await client.delete(
            path,
            params={"expectedAccessRevision": 2},
            headers=_WRITE | {"Idempotency-Key": "lost-delete-response"},
        )
        assert deleted.status_code == 200
        del deleted
        recovered = await client.post("/v1/operations/lookup", json=query, headers=_WRITE)
        assert recovered.status_code == 200
        original = recovered.json()
        assert set(original) == {
            "outcome",
            "operationId",
            "jobState",
            "admissionConfirmed",
            "accessBlocked",
            "applicationShutdownComplete",
            "physicalCleanupComplete",
            "retentionExpiresAt",
        }
        assert (
            original["outcome"] == "retained"
            and original["jobState"] is None
            and original["applicationShutdownComplete"] is None
        )
        assert (
            original["admissionConfirmed"]
            is original["accessBlocked"]
            is original["physicalCleanupComplete"]
            is True
        )
        operation = original["operationId"]
        assert (
            await client.get(
                "/v1/deletions/status", params={"operationId": operation}, headers=_BEARER
            )
        ).json() == original
        assert (
            await client.delete(
                path,
                params={"expectedAccessRevision": 2},
                headers=_WRITE | {"Idempotency-Key": "lost-delete-response"},
            )
        ).status_code == 404
        async with database.session() as session, session.begin():
            if ordinary_history == "removed":
                await session.execute(
                    delete(IdempotencyReservationRow).where(
                        IdempotencyReservationRow.operation_id == operation
                    )
                )
            else:
                native = await session.get(IdempotencyReservationRow, operation)
                assert native is not None
                native.expires_at = native.created_at + timedelta(microseconds=1)
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id
                    == seed.access.actor_principal_id.value,
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == project.project_id.value,
                    ProjectMembershipRow.principal_id == seed.access.actor_principal_id.value,
                )
            )
        # Neither path requires current Project membership or renews captured expiry.
        for _ in range(2):
            response = await client.post("/v1/operations/lookup", json=query, headers=_WRITE)
            known = await client.get(
                "/v1/deletions/status", params={"operationId": operation}, headers=_BEARER
            )
            assert (
                response.status_code == known.status_code == 200
                and response.json() == known.json() == original
            )
        for wrong in (
            {**query, "key": "wrong-original-key"},
            {**query, "organizationId": str(uuid4())},
            {**query, "installationId": str(uuid4())},
            {
                **query,
                "requestedRoute": f"/v1/projects/{project.project_id.value}/access-groups/{uuid4()}",
            },
        ):
            response = await client.post("/v1/operations/lookup", json=wrong, headers=_WRITE)
            assert response.status_code == 200 and response.json() == {"outcome": "unresolved"}
        async with database.session() as session, session.begin():
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
                )
                .values(version=2)
            )
        assert (
            await client.get(
                "/v1/deletions/status", params={"operationId": operation}, headers=_BEARER
            )
        ).status_code == 401
        assert (
            await client.post("/v1/operations/lookup", json=query, headers=_BEARER)
        ).status_code == 401


@pytest.mark.parametrize("corruption", ["job", "shutdown", "expiry-extension", "expired"])
async def test_both_recovery_entries_share_group_null_consistency_and_captured_expiry(
    database: Database, corruption: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    group = (await create_group(database, seed.access, project.project_id)).group
    app = group_http_application(
        database, seed.access, AccessContextDTO(seed.access.actor_principal_id, seed.binding)
    )
    installed = await PostgresInstallationIdentityReader(database).read()
    path = f"/v1/projects/{project.project_id.value}/access-groups/{group.group_id.value}"
    query = {
        "installationId": str(installed.value),
        "organizationId": str(seed.organization_id.value),
        "projectId": str(project.project_id.value),
        "method": "DELETE",
        "requestedRoute": path,
        "key": "settled-group",
        "expectedAuthority": {"family": "access_group_deletion", "actionId": "delete-access-group"},
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(
            path,
            params={"expectedAccessRevision": 2},
            headers=_WRITE | {"Idempotency-Key": "settled-group"},
        )
        assert response.status_code == 200
        operation = response.json()["operationId"]
        async with database.session() as session, session.begin():
            row = await session.get(DeletionStatusObservationRow, operation)
            binding = await session.get(DeletionStatusBindingRow, operation)
            assert row is not None and binding is not None and row.expires_at is not None
            if corruption == "job":
                row.job_status = "succeeded"
            elif corruption == "shutdown":
                row.application_shutdown_complete = True
            elif corruption == "expiry-extension":
                row.expires_at += timedelta(seconds=1)
            else:
                now = datetime.now(UTC)
                binding.recorded_at = now - timedelta(days=40)
                started = now - timedelta(days=31)
                row.retention_started_at = started
                row.owner_observed_at = started
                row.expires_at = started + timedelta(days=30)
        key_response = await client.post("/v1/operations/lookup", json=query, headers=_WRITE)
        id_response = await client.get(
            "/v1/deletions/status", params={"operationId": operation}, headers=_BEARER
        )
        if corruption == "expired":
            assert key_response.status_code == id_response.status_code == 200
            assert key_response.json() == id_response.json() == {"outcome": "unresolved"}
        else:
            assert key_response.status_code == id_response.status_code == 503


async def test_current_eligible_noninitiator_cannot_read_either_retained_entry(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    group = (await create_group(database, seed.actor.access, seed.project.project_id)).group
    removed = await delete_group(database, seed.actor.access, group, 2)
    bob = seed.bob_access
    app = group_http_application(database, bob, bob)
    installed = await PostgresInstallationIdentityReader(database).read()
    body = {
        "installationId": str(installed.value),
        "organizationId": str(seed.actor.organization_id.value),
        "projectId": str(group.project_id.value),
        "method": "DELETE",
        "requestedRoute": f"/v1/projects/{group.project_id.value}/access-groups/{group.group_id.value}",
        "key": "delete-support-group",
        "expectedAuthority": {"family": "access_group_deletion", "actionId": "delete-access-group"},
    }
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unknown = await client.post("/v1/operations/lookup", json=body, headers=_WRITE)
        known = await client.get(
            "/v1/deletions/status",
            params={"operationId": removed.operation.operation_id.value},
            headers=_COOKIE,
        )
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json() == {"outcome": "unresolved"}
