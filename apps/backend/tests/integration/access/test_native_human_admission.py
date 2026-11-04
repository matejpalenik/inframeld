"""Qualify ordinary admission through production HTTP, real Ory and PostgreSQL.

The existing fixture stages Alice's first-administrator proof. It does not supply
the missing supported first-unadmitted-human proof or private starter journey.
"""

import os
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.support.first_administrator_bootstrap_scenarios import (
    FirstAdministratorScenarioDTO,
    bootstrap_scenario,
)
from tests.support.hydra_provider import (
    API_AUDIENCE,
    HYDRA_ISSUER,
    HydraTestProvider,
    IssuedHydraTokensDTO,
    hydra_test_provider,
)
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_admin import disable_identity
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human
from tests.support.project_metadata_maintenance_command import run_project_metadata_maintenance

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
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
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
        reason="Requires private Kratos/Hydra and PostgreSQL integration services",
    ),
]
HEADERS = {
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "admit-bob",
}


async def _bootstrap_alice(
    database: Database,
    settings: DatabaseSettings,
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    browser: httpx2.AsyncClient,
) -> tuple[FirstAdministratorScenarioDTO, IssuedHydraTokensDTO, UUID]:
    identity = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), alice.subject)
    scenario = await bootstrap_scenario(database, identity=identity)
    tokens = await provider.issue_tokens(
        alice, browser=browser, credential_binding=scenario.binding
    )
    status, admitted, diagnostics = await run_project_metadata_maintenance(
        {
            "schemaVersion": 1,
            "mode": "bootstrap-first-administrator",
            "expectedInstallationId": str(scenario.binding.installation_id.value),
            "operationId": "native-admission-alice",
            "expectedAccessRevision": 0,
            "expectedIdentityId": alice.subject.value,
            "operatorLabel": "Native test operator",
            "reason": "Qualify ordinary human admission",
            "identityProof": {
                "kind": "hydra-access-token",
                "accessToken": tokens.access_token.value,
            },
        },
        settings,
    )
    if tokens.access_token.value.encode() in diagnostics:
        pytest.fail("Proof appeared in maintenance diagnostics.", pytrace=False)
    assert status == 0 and admitted.get("outcome") == "bootstrapped", (
        "Native Alice bootstrap failed."
    )
    async with database.session() as session:
        organization = await session.scalar(select(OrganizationRow.id))
    assert organization is not None
    return scenario, tokens, organization


def _settings(
    database: DatabaseSettings, *, hydra: bool = False, admin_url: str | None = KRATOS_ADMIN_URL
) -> ApplicationSettings:
    return get_settings().model_copy(
        update={
            "database": database,
            "kratos": KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                admin_url=HttpUrl(admin_url) if admin_url is not None else None,
                authority=IdentityAuthority("kratos:test"),
            ),
            "hydra": HydraSettings(
                admin_url=HttpUrl(HYDRA_ADMIN_URL),
                issuer=HYDRA_ISSUER,
                api_audience=API_AUDIENCE,
            )
            if hydra
            else None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )


def _assert_safe_problem(response: httpx2.Response, status: int, code: str, *secrets: str) -> None:
    if any(secret and secret in response.text for secret in secrets):
        pytest.fail("A credential appeared in a problem response.", pytrace=False)
    assert response.status_code == status, "Unexpected native admission status."
    assert response.json()["code"] == code
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"


async def _assert_admission_counts(
    database: Database, bob: RegisteredHumanDTO, *, operations: int, revision: int
) -> None:
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == (
            2 if operations else 1
        )
        link = await session.get(HumanIdentityLinkRow, ("kratos:test", bob.subject.value))
        assert (link is not None) is bool(operations)
        assert await session.scalar(select(OrganizationRow.access_revision)) == revision
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == operations
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
            == operations
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
            == operations
        )
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 0
        assert await session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow)) == 4
        )


async def test_cookie_admission_without_hydra_preserves_201_200_originals_and_never_repairs(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with (
        hydra_test_provider() as provider,
        create_browser() as alice_browser,
        create_browser() as bob_browser,
    ):
        alice = await register_human(alice_browser)
        bob = await register_human(bob_browser)
        await _bootstrap_alice(
            database, temporary_postgres_settings, provider, alice, alice_browser
        )
        async with database.session() as session:
            organization = await session.scalar(select(OrganizationRow.id))
        assert organization is not None
        route = f"/v1/organizations/{organization}/human-admissions"
        body = {"identityId": bob.subject.value, "expectedAccessRevision": 1}
        with TestClient(
            create_app(_settings(temporary_postgres_settings)), raise_server_exceptions=False
        ) as client:
            client.cookies.set("ory_kratos_session", alice.credential.value)
            assert client.get("/v1/session").status_code == 200
            csrf_denied = client.post(route, json=body, headers={"Idempotency-Key": "csrf-denied"})
            _assert_safe_problem(csrf_denied, 403, "access_denied", alice.credential.value)
            await _assert_admission_counts(database, bob, operations=0, revision=1)
            first = client.post(route, json=body, headers=HEADERS)
            assert first.status_code == 201, "Native cookie admission failed with Hydra disabled."
            original = first.json()
            assert original["organizationId"] == str(organization)
            assert original["changed"] is True and original["accessRevision"] == 2
            client.cookies.set("ory_kratos_session", bob.credential.value)
            current_bob = client.get("/v1/session")
            assert (
                current_bob.status_code == 200
                and current_bob.json()["principalId"] == original["principalId"]
            )
            client.cookies.set("ory_kratos_session", alice.credential.value)
            async with database.session() as session, session.begin():
                await session.execute(
                    delete(HumanCredentialVersionRow).where(
                        HumanCredentialVersionRow.subject == bob.subject.value
                    )
                )
                await session.execute(update(OrganizationRow).values(access_revision=9))
            replay = client.post(route, json=body, headers=HEADERS)
            assert replay.status_code == 201 and replay.json() == original
            fresh_body = {**body, "expectedAccessRevision": 9}
            fresh_headers = {**HEADERS, "Idempotency-Key": "already-admitted"}
            unchanged = client.post(route, json=fresh_body, headers=fresh_headers)
            assert unchanged.status_code == 200
            assert unchanged.json()["changed"] is False and unchanged.json()["accessRevision"] == 9
            assert unchanged.json()["principalId"] == original["principalId"]
            unchanged_replay = client.post(route, json=fresh_body, headers=fresh_headers)
            assert (
                unchanged_replay.status_code == 200 and unchanged_replay.json() == unchanged.json()
            )
            for response in (first, replay, unchanged, unchanged_replay):
                assert response.headers["cache-control"] == "no-store"
        await _assert_admission_counts(database, bob, operations=2, revision=9)
        async with database.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HumanCredentialVersionRow)
                    .where(HumanCredentialVersionRow.subject == bob.subject.value)
                )
                == 0
            )


@pytest.mark.parametrize(
    "change,status,code",
    [
        ("revoked-authority", 403, "access_denied"),
        ("stale-oauth", 401, "http_error"),
        ("suspended-bob", 409, "conflict"),
        ("inactive-provider-bob", 409, "conflict"),
    ],
)
async def test_human_oauth_replay_requires_current_actor_and_exact_recipient(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    change: str,
    status: int,
    code: str,
) -> None:
    async with (
        hydra_test_provider() as provider,
        create_browser() as alice_browser,
        create_browser() as bob_browser,
    ):
        alice = await register_human(alice_browser)
        bob = await register_human(bob_browser)
        scenario, tokens, organization = await _bootstrap_alice(
            database, temporary_postgres_settings, provider, alice, alice_browser
        )
        route = f"/v1/organizations/{organization}/human-admissions"
        body = {"identityId": bob.subject.value, "expectedAccessRevision": 1}
        with TestClient(
            create_app(_settings(temporary_postgres_settings, hydra=True)),
            raise_server_exceptions=False,
        ) as client:
            client.cookies.set("ory_kratos_session", alice.credential.value)
            first = client.post(route, json=body, headers=HEADERS)
            assert first.status_code == 201, "Native initial admission failed."
            original = first.json()
            client.cookies.clear()
            bearer = {
                "Authorization": f"Bearer {tokens.access_token.value}",
                "Idempotency-Key": "admit-bob",
            }
            replay = client.post(route, json=body, headers=bearer)
            assert replay.status_code == 201 and replay.json() == original
            if change == "inactive-provider-bob":
                await disable_identity(bob.subject)
            else:
                async with database.session() as session, session.begin():
                    if change == "revoked-authority":
                        await session.execute(
                            delete(OrganizationActionGrantRow).where(
                                OrganizationActionGrantRow.action == "admit-users"
                            )
                        )
                    elif change == "stale-oauth":
                        await session.execute(
                            update(HumanCredentialVersionRow)
                            .where(
                                HumanCredentialVersionRow.installation_id
                                == scenario.binding.installation_id.value,
                                HumanCredentialVersionRow.subject == alice.subject.value,
                            )
                            .values(version=scenario.binding.version.value + 1)
                        )
                    else:
                        await session.execute(
                            update(PrincipalRow)
                            .where(PrincipalRow.id == UUID(original["principalId"]))
                            .values(status=PrincipalStatus.SUSPENDED)
                        )
            denied = client.post(route, json=body, headers=bearer)
            _assert_safe_problem(
                denied, status, code, tokens.access_token.value, alice.credential.value
            )
        async with database.session() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(HumanAdmissionOperationResultRow)
                )
                == 1
            )
            assert (
                await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
                == 1
            )
            assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
            assert await session.scalar(select(OrganizationRow.access_revision)) == 2
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AccessAuditEventRow)
                    .where(AccessAuditEventRow.event_type == "human_admitted")
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(HumanCredentialVersionRow.version).where(
                        HumanCredentialVersionRow.subject == bob.subject.value
                    )
                )
                == 1
            )


@pytest.mark.parametrize(
    "admin_url", [None, "http://127.0.0.1:1"], ids=["not-configured", "unavailable"]
)
async def test_cookie_session_survives_missing_admin_but_admission_fails_closed(
    database: Database, temporary_postgres_settings: DatabaseSettings, admin_url: str | None
) -> None:
    async with (
        hydra_test_provider() as provider,
        create_browser() as alice_browser,
        create_browser() as bob_browser,
    ):
        alice = await register_human(alice_browser)
        bob = await register_human(bob_browser)
        _, _, organization = await _bootstrap_alice(
            database, temporary_postgres_settings, provider, alice, alice_browser
        )
        with TestClient(
            create_app(_settings(temporary_postgres_settings, admin_url=admin_url)),
            raise_server_exceptions=False,
        ) as client:
            client.cookies.set("ory_kratos_session", alice.credential.value)
            assert client.get("/v1/session").status_code == 200
            response = client.post(
                f"/v1/organizations/{organization}/human-admissions",
                json={"identityId": bob.subject.value, "expectedAccessRevision": 1},
                headers=HEADERS,
            )
            _assert_safe_problem(response, 503, "dependency_unavailable", alice.credential.value)
        await _assert_admission_counts(database, bob, operations=0, revision=1)
