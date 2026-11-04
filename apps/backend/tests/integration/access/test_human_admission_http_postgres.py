"""Exercise registered admission HTTP with real SQL and controlled provider verification."""

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, seed_project_creator

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_admission_operation_result_row import (
    HumanAdmissionOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
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
BOB_ID = UUID(int=200)
HEADERS = {
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "original",
}


def _settings(
    database: DatabaseSettings, seed: ProjectCreationSeedDTO, *, admin: bool = True
) -> ApplicationSettings:
    return get_settings().model_copy(
        update={
            "database": database,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test") if admin else None,
                authority=seed.binding.identity.authority,
            ),
            "hydra": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )


def _bob(seed: ProjectCreationSeedDTO) -> VerifiedHumanIdentityDTO:
    return VerifiedHumanIdentityDTO(seed.binding.identity.authority, IdentitySubject(str(BOB_ID)))


async def _assert_no_admission(database: Database, seed: ProjectCreationSeedDTO) -> None:
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert (
            await session.get(HumanIdentityLinkRow, (_bob(seed).authority.value, str(BOB_ID)))
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
        assert await session.scalar(select(OrganizationRow.access_revision)) == 1


async def test_registered_cookie_admission_preserves_original_and_no_change_receipts(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    route = f"/v1/organizations/{seed.organization_id.value}/human-admissions"
    body = {"identityId": str(BOB_ID), "expectedAccessRevision": 1}
    with (
        patch.object(
            KratosBrowserSessionVerifier, "verify", AsyncMock(return_value=seed.binding.identity)
        ),
        patch.object(KratosHumanIdentityVerifier, "verify", AsyncMock(return_value=_bob(seed))),
        TestClient(create_app(_settings(temporary_postgres_settings, seed))) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-alice")
        first = client.post(route, json=body, headers=HEADERS)
        assert first.status_code == 201
        original = first.json()
        assert set(original) == {
            "operationId",
            "idempotencyExpiresAt",
            "organizationId",
            "principalId",
            "accessRevision",
            "changed",
        }
        assert original["organizationId"] == str(seed.organization_id.value)
        assert original["changed"] is True and original["accessRevision"] == 2
        bob_principal = UUID(original["principalId"])
        async with database.session() as session, session.begin():
            await session.execute(
                delete(HumanCredentialVersionRow).where(
                    HumanCredentialVersionRow.subject == str(BOB_ID)
                )
            )
            await session.execute(update(OrganizationRow).values(access_revision=9))

        replay = client.post(route, json=body, headers=HEADERS)
        assert replay.status_code == 201 and replay.json() == original
        unchanged = client.post(
            route,
            json={**body, "expectedAccessRevision": 9},
            headers={**HEADERS, "Idempotency-Key": "already-admitted"},
        )
        assert unchanged.status_code == 200
        no_change = unchanged.json()
        assert no_change["principalId"] == str(bob_principal)
        assert no_change["changed"] is False and no_change["accessRevision"] == 9
        no_change_replay = client.post(
            route,
            json={**body, "expectedAccessRevision": 9},
            headers={**HEADERS, "Idempotency-Key": "already-admitted"},
        )
        assert no_change_replay.status_code == 200 and no_change_replay.json() == no_change
        for response in (first, replay, unchanged, no_change_replay):
            assert response.headers["cache-control"] == "no-store"
        async with database.session() as session, session.begin():
            await session.execute(
                delete(OrganizationActionGrantRow).where(
                    OrganizationActionGrantRow.action == "admit-users"
                )
            )
        denied = client.post(route, json=body, headers=HEADERS)
        assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
        assert denied.headers["cache-control"] == "no-store"

    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert await session.scalar(select(OrganizationRow.access_revision)) == 9
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 2
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.event_type.in_(
                        ["human_admitted", "human_admission_unchanged"]
                    )
                )
            )
            == 2
        )


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("missing-csrf", 403, "access_denied"),
        ("missing-cookie", 401, "http_error"),
        ("foreign-org", 404, "resource_not_found"),
        ("stale-revision", 409, "stale_revision"),
    ],
)
async def test_registered_http_denial_has_no_admission_effects(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    case: str,
    status: int,
    code: str,
) -> None:
    seed = await seed_project_creator(database)
    organization = uuid4() if case == "foreign-org" else seed.organization_id.value
    body = {
        "identityId": str(BOB_ID),
        "expectedAccessRevision": 0 if case == "stale-revision" else 1,
    }
    headers = dict(HEADERS)
    if case == "missing-csrf":
        del headers["X-Inframeld-CSRF"]
    with (
        patch.object(
            KratosBrowserSessionVerifier, "verify", AsyncMock(return_value=seed.binding.identity)
        ),
        patch.object(KratosHumanIdentityVerifier, "verify", AsyncMock(return_value=_bob(seed))),
        TestClient(create_app(_settings(temporary_postgres_settings, seed))) as client,
    ):
        if case != "missing-cookie":
            client.cookies.set("ory_kratos_session", "controlled-alice")
        response = client.post(
            f"/v1/organizations/{organization}/human-admissions", json=body, headers=headers
        )
        assert response.status_code == status
        assert response.json()["code"] == code
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["cache-control"] == "no-store"
    await _assert_no_admission(database, seed)


async def test_registered_provider_failure_is_safe_and_rolls_back(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    with (
        patch.object(
            KratosBrowserSessionVerifier, "verify", AsyncMock(return_value=seed.binding.identity)
        ),
        patch.object(
            KratosHumanIdentityVerifier,
            "verify",
            AsyncMock(side_effect=DependencyUnavailableError()),
        ),
        TestClient(create_app(_settings(temporary_postgres_settings, seed))) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-alice")
        response = client.post(
            f"/v1/organizations/{seed.organization_id.value}/human-admissions",
            json={"identityId": str(BOB_ID), "expectedAccessRevision": 1},
            headers=HEADERS,
        )
        assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
        assert response.headers["cache-control"] == "no-store"
    await _assert_no_admission(database, seed)


async def test_missing_admin_preserves_cookie_authentication_but_cannot_admit(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    with (
        patch.object(
            KratosBrowserSessionVerifier, "verify", AsyncMock(return_value=seed.binding.identity)
        ),
        TestClient(create_app(_settings(temporary_postgres_settings, seed, admin=False))) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-alice")
        current = client.get("/v1/session")
        assert current.status_code == 200
        assert current.json()["principalId"] == str(seed.access.actor_principal_id.value)
        response = client.post(
            f"/v1/organizations/{seed.organization_id.value}/human-admissions",
            json={"identityId": str(BOB_ID), "expectedAccessRevision": 1},
            headers=HEADERS,
        )
        assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
        assert response.headers["cache-control"] == "no-store"
    await _assert_no_admission(database, seed)
