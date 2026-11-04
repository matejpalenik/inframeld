"""Follow registered human HTTP contracts through real admission and membership writes."""

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, seed_project_creator
from tests.support.project_membership_postgres_scenarios import seed_membership_project

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.hydra_access_token_verifier import (
    HydraAccessTokenVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
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
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
HEADERS = {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}


def _settings(
    database: DatabaseSettings, actor: ProjectCreationSeedDTO, *, bearer: bool = False
) -> ApplicationSettings:
    return get_settings().model_copy(
        update={
            "database": database,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test"),
                authority=actor.binding.identity.authority,
            ),
            "hydra": HydraSettings(
                admin_url=HttpUrl("http://hydra-admin.test"),
                public_url=HttpUrl("https://auth.test"),
                issuer=OAuthIssuer("https://auth.test/"),
                api_audience=HumanAPIAudience("https://api.test"),
            )
            if bearer
            else None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )


async def test_registered_cookie_admission_creation_membership_and_replay_preserve_current_state(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    actor = await seed_project_creator(database)
    bob_identity = VerifiedHumanIdentityDTO(
        actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    browser = AsyncMock(return_value=actor.binding.identity)
    with (
        patch.object(KratosBrowserSessionVerifier, "verify", browser),
        patch.object(KratosHumanIdentityVerifier, "verify", AsyncMock(return_value=bob_identity)),
    ):
        application = create_app(_settings(temporary_postgres_settings, actor))
        async with (
            application.router.lifespan_context(application),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=application),
                base_url="https://api.test",
                headers=HEADERS,
                cookies={"ory_kratos_session": "controlled-alice"},
            ) as client,
        ):
            admission = await client.post(
                f"/v1/organizations/{actor.organization_id.value}/human-admissions",
                json={"identityId": str(UUID(int=200)), "expectedAccessRevision": 1},
                headers={"Idempotency-Key": "admit-bob"},
            )
            assert admission.status_code == 201
            bob = admission.json()["principalId"]
            creation = await client.post(
                "/v1/projects",
                json={
                    "organizationId": str(actor.organization_id.value),
                    "expectedAccessRevision": admission.json()["accessRevision"],
                    "name": "support",
                    "displayName": "Support",
                },
                headers={"Idempotency-Key": "create-support"},
            )
            assert creation.status_code == 201
            project = creation.json()["projectId"]
            route = f"/v1/projects/{project}/members/{bob}"
            del client.headers["X-Inframeld-CSRF"]
            csrf = await client.put(
                route, json={"expectedAccessRevision": 1}, headers={"Idempotency-Key": "add-bob"}
            )
            assert csrf.status_code == 403
            assert csrf.json()["code"] == "access_denied"
            assert csrf.headers["cache-control"] == "no-store"
            async with database.session() as session:
                assert await session.get(ProjectMembershipRow, (UUID(project), UUID(bob))) is None
                current_project = await session.get(ProjectRow, UUID(project))
                assert current_project is not None and current_project.access_revision == 1
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ProjectMembershipOperationResultRow)
                        .where(
                            ProjectMembershipOperationResultRow.project_id == UUID(project),
                            ProjectMembershipOperationResultRow.principal_id == UUID(bob),
                        )
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(IdempotencyReservationRow)
                        .where(
                            IdempotencyReservationRow.project_id == UUID(project),
                            IdempotencyReservationRow.principal_id
                            == actor.access.actor_principal_id.value,
                            IdempotencyReservationRow.method == "PUT",
                            IdempotencyReservationRow.requested_route == route,
                            IdempotencyReservationRow.request_key == "add-bob",
                        )
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(AccessAuditEventRow)
                        .where(
                            AccessAuditEventRow.project_id == UUID(project),
                            AccessAuditEventRow.affected_principal_id == UUID(bob),
                            AccessAuditEventRow.event_type.in_(
                                (
                                    "project_member_added",
                                    "project_member_removed",
                                    "project_membership_unchanged",
                                )
                            ),
                        )
                    )
                    == 0
                )
            client.headers["X-Inframeld-CSRF"] = "1"
            added = await client.put(
                route, json={"expectedAccessRevision": 1}, headers={"Idempotency-Key": "add-bob"}
            )
            assert added.status_code == 201 and added.json()["member"] is True
            page = await client.get(f"/v1/projects/{project}/members")
            assert page.status_code == 200 and page.json()["accessRevision"] == 2
            assert {item["principalId"] for item in page.json()["items"]} == {
                str(actor.access.actor_principal_id.value),
                bob,
            }
            removed = await client.delete(
                route,
                params={"expectedAccessRevision": 2},
                headers={"Idempotency-Key": "leave-bob"},
            )
            assert removed.status_code == 200 and removed.json()["removed"] is True
            old_add = await client.put(
                route, json={"expectedAccessRevision": 1}, headers={"Idempotency-Key": "add-bob"}
            )
            assert old_add.status_code == 201 and old_add.json() == added.json()
            assert len((await client.get(f"/v1/projects/{project}/members")).json()["items"]) == 1
            rejoined = await client.put(
                route, json={"expectedAccessRevision": 3}, headers={"Idempotency-Key": "rejoin-bob"}
            )
            assert rejoined.status_code == 201
            old_remove = await client.delete(
                route,
                params={"expectedAccessRevision": 2},
                headers={"Idempotency-Key": "leave-bob"},
            )
            assert old_remove.status_code == 200 and old_remove.json() == removed.json()
            assert len((await client.get(f"/v1/projects/{project}/members")).json()["items"]) == 2
            async with database.session() as session, session.begin():
                await session.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == UUID(project),
                        ProjectActionGrantRow.recipient_principal_id
                        == actor.access.actor_principal_id.value,
                        ProjectActionGrantRow.action == "manage-project-members",
                    )
                )
            denied = await client.put(
                route, json={"expectedAccessRevision": 1}, headers={"Idempotency-Key": "add-bob"}
            )
            assert denied.status_code == 403
            for response in (added, removed, old_add, rejoined, old_remove, denied):
                assert response.headers["cache-control"] == "no-store"
    async with database.session() as session:
        assert await session.get(ProjectMembershipRow, (UUID(project), UUID(bob))) is not None
        assert await session.scalar(select(ProjectRow.access_revision)) == 4
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.recipient_principal_id == UUID(bob))
            )
            == 0
        )


async def test_registered_bearer_replay_rechecks_generation_changed_after_authentication(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_membership_project(database)
    original_authenticate = HumanAccessTokenAuthenticationService.authenticate

    async def authenticate_then_advance(
        self: HumanAccessTokenAuthenticationService, credential: HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        access = await original_authenticate(self, credential)
        async with database.session() as session, session.begin():
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id
                    == seed.actor.binding.installation_id.value,
                    HumanCredentialVersionRow.authority
                    == seed.actor.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.actor.binding.identity.subject.value,
                )
                .values(version=HumanCredentialVersionRow.version + 1)
            )
        return access

    with (
        patch.object(
            HydraAccessTokenVerifier, "verify", AsyncMock(return_value=seed.actor.binding)
        ),
        patch.object(
            KratosHumanIdentityVerifier,
            "verify",
            AsyncMock(return_value=seed.actor.binding.identity),
        ),
    ):
        application = create_app(_settings(temporary_postgres_settings, seed.actor, bearer=True))
        async with (
            application.router.lifespan_context(application),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=application),
                base_url="https://api.test",
                headers={"Authorization": "Bearer controlled-membership-token"},
            ) as client,
        ):
            route = f"/v1/projects/{seed.project.project_id.value}/members/{seed.bob_id.value}"
            added = await client.put(
                route,
                json={"expectedAccessRevision": 1},
                headers={"Idempotency-Key": "bearer-join"},
            )
            assert added.status_code == 201
            with patch.object(
                HumanAccessTokenAuthenticationService, "authenticate", authenticate_then_advance
            ):
                replay = await client.put(
                    route,
                    json={"expectedAccessRevision": 1},
                    headers={"Idempotency-Key": "bearer-join"},
                )
            assert replay.status_code == 401
            assert replay.headers["www-authenticate"].lower().startswith("bearer")
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 1
        )
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )
