"""Follow staged Ory proof through installed admission and production creation HTTP.

The existing fixture stages its proof. This is not an operator proof-acquisition
procedure and does not add a first-user CLI proof producer.
"""

import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.support.first_administrator_bootstrap_scenarios import bootstrap_scenario
from tests.support.hydra_provider import API_AUDIENCE, HYDRA_ISSUER, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import create_browser, register_human
from tests.support.project_creation_scenarios import INITIAL_ACTIONS
from tests.support.project_metadata_maintenance_command import run_project_metadata_maintenance

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
        reason="Requires private Kratos/Hydra integration services",
    ),
]


async def test_first_administrator_cookie_creation_and_bearer_original_replay_use_current_authority(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with hydra_test_provider() as provider, create_browser() as browser:
        human = await register_human(browser)
        identity = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), human.subject)
        scenario = await bootstrap_scenario(database, identity=identity)
        tokens = await provider.issue_tokens(
            human, browser=browser, credential_binding=scenario.binding
        )
        status, admitted, diagnostics = await run_project_metadata_maintenance(
            {
                "schemaVersion": 1,
                "mode": "bootstrap-first-administrator",
                "expectedInstallationId": str(scenario.binding.installation_id.value),
                "operationId": "native-project-creator",
                "expectedAccessRevision": 0,
                "expectedIdentityId": human.subject.value,
                "operatorLabel": "Native test operator",
                "reason": "Qualify ordinary Project creation",
                "identityProof": {
                    "kind": "hydra-access-token",
                    "accessToken": tokens.access_token.value,
                },
            },
            temporary_postgres_settings,
        )
        if tokens.access_token.value.encode() in diagnostics:
            pytest.fail("Proof appeared in maintenance diagnostics.", pytrace=False)
        assert status == 0 and admitted.get("outcome") == "bootstrapped", "Native bootstrap failed."
        principal = admitted.get("principalId")
        assert isinstance(principal, str)
        creator_id = UUID(principal)

        settings = get_settings().model_copy(
            update={
                "database": temporary_postgres_settings,
                "kratos": KratosSettings(
                    public_url=HttpUrl(KRATOS_PUBLIC_URL),
                    admin_url=HttpUrl(KRATOS_ADMIN_URL),
                    authority=identity.authority,
                ),
                "hydra": HydraSettings(
                    admin_url=HttpUrl(HYDRA_ADMIN_URL),
                    issuer=HYDRA_ISSUER,
                    api_audience=API_AUDIENCE,
                ),
                "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            }
        )
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            client.cookies.set("ory_kratos_session", human.credential.value)
            own = client.get("/v1/my-organization-access")
            assert own.status_code == 200
            assert own.json()["principalId"] == principal
            assert own.json()["accessRevision"] == 1
            assert {item["actionId"] for item in own.json()["grants"]} == {
                "admit-users",
                "suspend-users",
                "restore-users",
                "create-projects",
            }
            body = {
                "organizationId": own.json()["organizationId"],
                "expectedAccessRevision": 1,
                "name": "native-support",
                "displayName": "Native support",
            }
            headers = {
                "Idempotency-Key": "native-creation",
                "Origin": "https://account.test",
                "X-Inframeld-CSRF": "1",
            }
            csrf_denied = client.post(
                "/v1/projects", json=body, headers={"Idempotency-Key": "csrf-denied"}
            )
            assert csrf_denied.status_code == 403
            first = client.post("/v1/projects", json=body, headers=headers)
            assert first.status_code == 201, "Native cookie creation failed."
            original = first.json()
            assert original["initialGrants"] == [
                {
                    "target": {"kind": "project", "projectId": original["projectId"]},
                    "actionId": action,
                    "canGrant": True,
                }
                for action in INITIAL_ACTIONS
            ]
            client.cookies.clear()
            bearer = {
                "Authorization": f"Bearer {tokens.access_token.value}",
                "Idempotency-Key": "native-creation",
            }
            own_bearer = client.get("/v1/my-organization-access", headers=bearer)
            assert own_bearer.status_code == 200 and own_bearer.json() == own.json()
            replay = client.post("/v1/projects", json=body, headers=bearer)
            assert replay.status_code == 201 and replay.json() == original
            assert replay.headers["cache-control"] == first.headers["cache-control"] == "no-store"
            app_key = client.post(
                "/v1/projects",
                json=body,
                headers={
                    "Authorization": "Bearer ifm_app_unsupported",
                    "Idempotency-Key": "app-key",
                },
            )
            assert app_key.status_code == 401

            async with database.session() as session, session.begin():
                project_id = UUID(original["projectId"])
                project = await session.get(ProjectRow, project_id)
                assert project is not None and (
                    project.access_revision,
                    project.metadata_revision,
                ) == (1, 0)
                assert (project.resource_name, project.name) == ("native-support", "Native support")
                member = await session.get(ProjectMembershipRow, (project_id, creator_id))
                assert member is not None and member.assigned_by_principal_id == creator_id
                grants = (
                    await session.scalars(
                        select(ProjectActionGrantRow).where(
                            ProjectActionGrantRow.project_id == project_id
                        )
                    )
                ).all()
                assert len(grants) == 18 and {grant.action for grant in grants} == set(
                    INITIAL_ACTIONS
                )
                assert all(
                    grant.can_grant and grant.assigned_by_principal_id == member.principal_id
                    for grant in grants
                )
                name = await session.get(
                    ProjectNameReservationRow, (project.organization_id, "native-support")
                )
                assert name is not None and name.binding_revision == 0 and not name.retired
                receipt = await session.get(
                    ProjectCreationOperationResultRow, original["operationId"]
                )
                assert (
                    receipt is not None
                    and receipt.project_id == project_id
                    and tuple(receipt.initial_actions) == INITIAL_ACTIONS
                )
                reservation = await session.get(IdempotencyReservationRow, original["operationId"])
                assert reservation is not None and reservation.project_id is None
                assert reservation.organization_id == project.organization_id
                assert (
                    reservation.lookup_authority_family == "organization_action_use"
                    and reservation.lookup_action_id == "create-projects"
                )
                assert await session.scalar(select(OrganizationRow.access_revision)) == 1
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(AccessAuditEventRow)
                        .where(AccessAuditEventRow.event_type == "project_created")
                    )
                    == 1
                )
                await session.execute(delete(OrganizationActionGrantRow))
            empty = client.get("/v1/my-organization-access", headers=bearer)
            assert empty.status_code == 200 and empty.json()["grants"] == []
            denied = client.post("/v1/projects", json=body, headers=bearer)
            assert denied.status_code == 403 and "projectId" not in denied.json()
            async with database.session() as session, session.begin():
                await session.execute(
                    update(HumanCredentialVersionRow)
                    .where(
                        HumanCredentialVersionRow.installation_id
                        == scenario.binding.installation_id.value,
                        HumanCredentialVersionRow.authority == identity.authority.value,
                        HumanCredentialVersionRow.subject == identity.subject.value,
                    )
                    .values(version=scenario.binding.version.value + 1)
                )
            assert await provider.token_is_active(tokens.access_token)
            stale_read = client.get("/v1/my-organization-access", headers=bearer)
            stale_replay = client.post("/v1/projects", json=body, headers=bearer)
            assert stale_read.status_code == stale_replay.status_code == 401
            assert (
                stale_read.headers["cache-control"]
                == stale_replay.headers["cache-control"]
                == "no-store"
            )
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
                == 1
            )
