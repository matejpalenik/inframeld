"""Exercise registered Project deletion and retained lookup with real PostgreSQL effects."""

import asyncio
import os
from typing import override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ory_kratos_client.api.frontend_api import FrontendApi
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.integration.access.test_project_deletion_postgres import (
    DeletionScenario,
    seed_deletion_scenario,
)
from tests.integration.access.test_project_deletion_worker import claim, run_local

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap import access_composition
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.deletion_status_retention_settings import (
    DeletionStatusRetentionSettings,
)
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
HEADERS = {
    "Cookie": "ory_kratos_session=project-delete-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "http-delete-original",
}
ADMISSION_FIELDS = {
    "operationId",
    "idempotencyExpiresAt",
    "projectId",
    "accessRevision",
    "admissionConfirmed",
    "accessBlocked",
}
STATUS_FIELDS = {
    "outcome",
    "operationId",
    "jobState",
    "admissionConfirmed",
    "accessBlocked",
    "applicationShutdownComplete",
    "physicalCleanupComplete",
    "retentionExpiresAt",
}


class MockProjectCookieVerifier(BrowserSessionVerifier):
    def __init__(self, identity: VerifiedHumanIdentityDTO) -> None:
        self._identity = identity

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        return self._identity if credential.value == "project-delete-cookie" else None


def application(
    settings: DatabaseSettings,
    identity: VerifiedHumanIdentityDTO,
    monkeypatch: pytest.MonkeyPatch,
    *,
    days: int = 7,
) -> FastAPI:
    verifier = MockProjectCookieVerifier(identity)

    def provider_verifier(
        api: FrontendApi, authority: IdentityAuthority, *, timeout_seconds: float
    ) -> MockProjectCookieVerifier:
        return verifier

    monkeypatch.setattr(access_composition, "KratosBrowserSessionVerifier", provider_verifier)
    configured = get_settings().model_copy(
        update={
            "database": settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://unused-provider.invalid"), authority=identity.authority
            ),
            "hydra": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            "discovery": None,
            "deletion_status_retention": DeletionStatusRetentionSettings(days=days),
        }
    )
    return create_app(configured)


def path(scope: DeletionScenario) -> str:
    return f"/v1/projects/{scope.defaults.project_id.value}"


async def original_lookup_body(database: Database, scope: DeletionScenario) -> dict[str, object]:
    async with database.session() as session:
        installation = await session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
    assert installation is not None
    return {
        "installationId": str(installation),
        "organizationId": str(scope.defaults.actor.organization_id.value),
        "projectId": str(scope.defaults.project_id.value),
        "method": "DELETE",
        "requestedRoute": path(scope),
        "key": HEADERS["Idempotency-Key"],
        "expectedAuthority": {"family": "project_deletion", "actionId": "delete-project"},
    }


async def test_registered_delete_captures_nondefault_retention_and_replays_original_202(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_deletion_scenario(database)
    with TestClient(
        application(
            temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch, days=7
        )
    ) as client:
        first = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert first.status_code == 202, first.text
        assert set(first.json()) == ADMISSION_FIELDS
        assert first.json()["idempotencyExpiresAt"] is None
        assert first.json()["accessRevision"] == scope.revision + 1
        assert first.json()["admissionConfirmed"] is True and first.json()["accessBlocked"] is True
        assert first.headers["cache-control"] == "no-store"
        repeated = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert repeated.status_code == 202 and repeated.json() == first.json()
        assert (
            client.delete(
                path(scope),
                params={"expectedAccessRevision": scope.revision + 1},
                headers=HEADERS | {"Idempotency-Key": "fresh-after-block"},
            ).status_code
            == 409
        )
    async with database.session() as session:
        binding = await session.get(DeletionStatusBindingRow, first.json()["operationId"])
        assert binding is not None and binding.retention_days == 7
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        recorded = binding.recorded_at
    with TestClient(
        application(
            temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch, days=90
        )
    ) as client:
        replay = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert replay.status_code == 202 and replay.json() == first.json()
    async with database.session() as session:
        binding = await session.get(DeletionStatusBindingRow, first.json()["operationId"])
        assert (
            binding is not None and binding.retention_days == 7 and binding.recorded_at == recorded
        )


async def test_registered_lookup_recovers_original_after_native_and_membership_removal(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deletion_scope = await seed_deletion_scenario(database)
    with TestClient(
        application(
            temporary_postgres_settings, deletion_scope.defaults.actor.binding.identity, monkeypatch
        )
    ) as client:
        accepted = client.delete(
            path(deletion_scope),
            params={"expectedAccessRevision": deletion_scope.revision},
            headers=HEADERS,
        )
        assert accepted.status_code == 202, accepted.text
    body = await original_lookup_body(database, deletion_scope)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == accepted.json()["operationId"]
            )
        )
    async with database.session() as session, session.begin():
        actor = deletion_scope.defaults.actor.access.actor_principal_id.value
        # This controlled disappearance exercises status authority, not shutdown effects.
        await session.execute(
            delete(GroupActionGrantRow).where(
                GroupActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                GroupActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == deletion_scope.defaults.project_id.value,
                GroupManagerRow.principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupMembershipRow).where(
                GroupMembershipRow.project_id == deletion_scope.defaults.project_id.value,
                GroupMembershipRow.principal_id == actor,
            )
        )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                ApplicationActionGrantRow.recipient_principal_id == actor,
                ApplicationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
            )
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == deletion_scope.defaults.project_id.value,
                ProjectMembershipRow.principal_id == actor,
            )
        )
    with TestClient(
        application(
            temporary_postgres_settings, deletion_scope.defaults.actor.binding.identity, monkeypatch
        )
    ) as client:
        assert (
            client.delete(
                path(deletion_scope),
                params={"expectedAccessRevision": deletion_scope.revision},
                headers=HEADERS,
            ).status_code
            == 404
        )
        recovered = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
        assert recovered.status_code == 200, recovered.text
        assert set(recovered.json()) == STATUS_FIELDS
        assert recovered.json()["operationId"] == accepted.json()["operationId"]
        assert recovered.json()["outcome"] == "retained"
        assert recovered.json()["admissionConfirmed"] is True
        assert recovered.json()["applicationShutdownComplete"] is False
        assert recovered.json()["physicalCleanupComplete"] is False
        assert recovered.json()["retentionExpiresAt"] is None
        assert recovered.headers["cache-control"] == "no-store"
        unknown = client.post(
            "/v1/operations/lookup", json=body | {"key": "different-original"}, headers=HEADERS
        )
        assert unknown.status_code == 200 and unknown.json() == {"outcome": "unresolved"}
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert await session.get(IdempotencyReservationRow, accepted.json()["operationId"]) is None


async def test_registered_lookup_denies_current_ineligible_original_and_hides_another_human(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_deletion_scenario(database)
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        assert (
            client.delete(
                path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
            ).status_code
            == 202
        )
    body = await original_lookup_body(database, scope)
    async with database.session() as session:
        bob = await session.scalar(
            select(HumanIdentityLinkRow).where(
                HumanIdentityLinkRow.principal_id == scope.defaults.bob_id.value
            )
        )
        assert bob is not None
        identity = VerifiedHumanIdentityDTO(
            IdentityAuthority(bob.authority), IdentitySubject(bob.subject)
        )
    with TestClient(application(temporary_postgres_settings, identity, monkeypatch)) as client:
        result = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
        assert result.status_code == 200 and result.json() == {"outcome": "unresolved"}
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == scope.defaults.actor.access.actor_principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        result = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
        assert result.status_code == 403


async def test_registered_replay_rechecks_delete_authority_before_original(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_deletion_scenario(database)
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        accepted = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert accepted.status_code == 202
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == scope.defaults.project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == scope.defaults.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "delete-project",
            )
        )
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        denied = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert denied.status_code == 403
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1


@pytest.mark.parametrize("invalid", ["query", "body", "key", "csrf", "origin"])
async def test_registered_invalid_transport_leaves_project_active(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    scope = await seed_deletion_scenario(database)
    route = path(scope) + f"?expectedAccessRevision={scope.revision}"
    headers = dict(HEADERS)
    content = b""
    if invalid == "query":
        route += f"&expectedAccessRevision={scope.revision}"
    elif invalid == "body":
        content = b"{}"
    elif invalid == "key":
        headers["Idempotency-Key"] = " "
    elif invalid == "csrf":
        del headers["X-Inframeld-CSRF"]
    else:
        headers["Origin"] = "https://untrusted.test"
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        result = client.request("DELETE", route, headers=headers, content=content)
        assert result.status_code == (403 if invalid in {"csrf", "origin"} else 422)
        assert result.headers["cache-control"] == "no-store"
    async with database.session() as session:
        project = await session.get(ProjectRow, scope.defaults.project_id.value)
        assert (
            project is not None
            and project.status is ProjectStatus.ACTIVE
            and project.access_revision == scope.revision
        )
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 0


async def test_registered_status_after_real_shutdown_keeps_physical_pending(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = await seed_deletion_scenario(database)
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        accepted = client.delete(
            path(scope), params={"expectedAccessRevision": scope.revision}, headers=HEADERS
        )
        assert accepted.status_code == 202
    context = await claim(database)
    await run_local(database, context)
    await ApplicationWorkerOperations(
        database, JobSettings(work_seconds=60), asyncio.Event()
    ).succeed(context)
    with TestClient(
        application(temporary_postgres_settings, scope.defaults.actor.binding.identity, monkeypatch)
    ) as client:
        result = client.get(
            "/v1/deletions/status",
            params={"operationId": accepted.json()["operationId"]},
            headers=HEADERS,
        )
        assert result.status_code == 200
        assert set(result.json()) == STATUS_FIELDS
        assert result.json()["jobState"] == "succeeded"
        assert result.json()["applicationShutdownComplete"] is True
        assert result.json()["physicalCleanupComplete"] is False
        assert result.json()["retentionExpiresAt"] is None
