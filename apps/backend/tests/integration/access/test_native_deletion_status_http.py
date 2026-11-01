"""Qualify registered status reads with real private Ory credentials and seeded read history."""

import os
from collections.abc import AsyncGenerator
from typing import Literal
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.deletion_status_scenarios import (
    DeletionStatusSeedDTO,
    MockDeletionStatusScenarios,
)
from tests.support.hydra_provider import (
    API_AUDIENCE,
    HYDRA_ISSUER,
    HydraTestProvider,
    hydra_test_provider,
)
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_admin import disable_identity
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

AUTHORITY = IdentityAuthority("kratos:test")
PATH = "/v1/deletions/status"
SAFE_FIELDS = {
    "outcome",
    "operationId",
    "jobState",
    "admissionConfirmed",
    "accessBlocked",
    "applicationShutdownComplete",
    "physicalCleanupComplete",
    "retentionExpiresAt",
}
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
        reason="Requires private Ory integration services",
    ),
]


@pytest_asyncio.fixture
async def provider() -> AsyncGenerator[HydraTestProvider]:
    async with hydra_test_provider() as provider:
        yield provider


@pytest_asyncio.fixture
async def human(provider: HydraTestProvider) -> RegisteredHumanDTO:
    async with create_browser(public_url=KRATOS_PUBLIC_URL) as browser:
        return await register_human(browser)


def _settings(
    database: DatabaseSettings, *, unavailable: Literal["hydra", "kratos"] | None = None
) -> ApplicationSettings:
    return get_settings().model_copy(
        update={
            "database": database,
            "kratos": KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                admin_url=HttpUrl(
                    "http://127.0.0.1:1" if unavailable == "kratos" else KRATOS_ADMIN_URL
                ),
                authority=AUTHORITY,
            ),
            "hydra": HydraSettings(
                admin_url=HttpUrl(
                    "http://127.0.0.1:1" if unavailable == "hydra" else HYDRA_ADMIN_URL
                ),
                issuer=HYDRA_ISSUER,
                api_audience=API_AUDIENCE,
            ),
        }
    )


async def _history(database: Database, human: RegisteredHumanDTO) -> DeletionStatusSeedDTO:
    """Read fixtures prove neither admitted deletion nor real owner completion."""
    async with database.session() as session, session.begin():
        return await MockDeletionStatusScenarios.seed_private_observation(
            session,
            days=7,
            age_days=2,
            identity=VerifiedHumanIdentityDTO(AUTHORITY, human.subject),
        )


async def _remove_project(database: Database, seed: DeletionStatusSeedDTO) -> None:
    assert seed.request.project_id is not None
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == seed.reservation.operation_id.value
            )
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == seed.request.project_id.value
            )
        )
        await session.execute(
            delete(ProjectRow).where(ProjectRow.id == seed.request.project_id.value)
        )


def _binding(seed: DeletionStatusSeedDTO) -> HumanOAuthCredentialBindingDTO:
    return HumanOAuthCredentialBindingDTO(
        seed.identity, seed.installation_id, HumanCredentialVersion(1)
    )


async def test_real_cookie_and_bearer_read_after_project_removal(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
) -> None:
    seed = await _history(database, human)
    tokens = await provider.issue_tokens(human, credential_binding=_binding(seed))
    await _remove_project(database, seed)
    with TestClient(
        create_app(_settings(temporary_postgres_settings)), raise_server_exceptions=False
    ) as client:
        bearer = client.get(
            PATH,
            params={"operationId": seed.reservation.operation_id.value},
            headers={"Authorization": f"Bearer {tokens.access_token.value}"},
        )
        assert bearer.status_code == 200, bearer.text
        assert set(bearer.json()) == SAFE_FIELDS
        assert bearer.json()["outcome"] == "retained"
        assert bearer.json()["physicalCleanupComplete"] is True
        client.cookies.set("ory_kratos_session", human.credential.value)
        cookie = client.get(PATH, params={"operationId": seed.reservation.operation_id.value})
        assert cookie.status_code == 200, cookie.text
        assert cookie.json() == bearer.json()
        assert cookie.headers["cache-control"] == bearer.headers["cache-control"] == "no-store"


async def _admit_privileged_noninitiator(
    session: AsyncSession, seed: DeletionStatusSeedDTO, human: RegisteredHumanDTO
) -> HumanOAuthCredentialBindingDTO:
    principal = uuid4()
    identity = VerifiedHumanIdentityDTO(AUTHORITY, human.subject)
    session.add(
        PrincipalRow(
            id=principal,
            organization_id=seed.request.organization_id.value,
            kind=PrincipalKind.HUMAN,
            status=PrincipalStatus.ACTIVE,
            display_name="Other administrator",
        )
    )
    await session.flush()
    session.add_all(
        [
            HumanIdentityLinkRow(
                authority=AUTHORITY.value,
                subject=human.subject.value,
                organization_id=seed.request.organization_id.value,
                principal_id=principal,
                principal_kind=PrincipalKind.HUMAN,
            ),
            HumanCredentialVersionRow(
                installation_id=seed.installation_id.value,
                authority=AUTHORITY.value,
                subject=human.subject.value,
                version=1,
            ),
            OrganizationActionGrantRow(
                organization_id=seed.request.organization_id.value,
                recipient_principal_id=principal,
                action="admit-users",
                recipient_kind=PrincipalKind.HUMAN,
                can_grant=True,
            ),
        ]
    )
    await session.flush()
    return HumanOAuthCredentialBindingDTO(identity, seed.installation_id, HumanCredentialVersion(1))


async def test_real_privileged_noninitiator_gets_no_match_specific_disclosure(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
) -> None:
    seed = await _history(database, human)
    await _remove_project(database, seed)
    async with create_browser(public_url=KRATOS_PUBLIC_URL) as browser:
        other = await register_human(browser)
    async with database.session() as session, session.begin():
        binding = await _admit_privileged_noninitiator(session, seed, other)
    tokens = await provider.issue_tokens(other, credential_binding=binding)
    headers = {"Authorization": f"Bearer {tokens.access_token.value}"}
    with TestClient(
        create_app(_settings(temporary_postgres_settings)), raise_server_exceptions=False
    ) as client:
        foreign = client.get(
            PATH, params={"operationId": seed.reservation.operation_id.value}, headers=headers
        )
        absent = client.get(PATH, params={"operationId": "never-retained"}, headers=headers)
    assert foreign.status_code == absent.status_code == 200, foreign.text
    assert foreign.json() == absent.json() == {"outcome": "unresolved"}
    assert foreign.headers["cache-control"] == absent.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "change",
    [
        "suspended",
        "recovery",
        "stale-generation",
        "revoked-token",
        "disabled-identity",
        "invalid-token",
    ],
)
async def test_real_credentials_and_current_ineligibility_cannot_read_retained_history(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
    change: str,
) -> None:
    seed = await _history(database, human)
    tokens = await provider.issue_tokens(human, credential_binding=_binding(seed))
    await _remove_project(database, seed)
    if change == "revoked-token":
        await provider.revoke_access_token(tokens.access_token)
    elif change == "disabled-identity":
        await disable_identity(human.subject)
    elif change in ("suspended", "recovery", "stale-generation"):
        async with database.session() as session, session.begin():
            if change == "suspended":
                await session.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            elif change == "stale-generation":
                await session.execute(
                    update(HumanCredentialVersionRow)
                    .where(
                        HumanCredentialVersionRow.installation_id == seed.installation_id.value,
                        HumanCredentialVersionRow.authority == seed.identity.authority.value,
                        HumanCredentialVersionRow.subject == seed.identity.subject.value,
                    )
                    .values(version=2)
                )
            else:
                session.add(
                    IdentityRecoveryAdmissionRow(
                        operation_id=str(uuid4()),
                        installation_id=seed.installation_id.value,
                        authority=seed.identity.authority.value,
                        subject=seed.identity.subject.value,
                        flow_id=uuid4(),
                        event_kind=IdentityRecoveryEventKind.RECOVERY,
                    )
                )
    token = "not-a-valid-access-token" if change == "invalid-token" else tokens.access_token.value
    with TestClient(
        create_app(_settings(temporary_postgres_settings)), raise_server_exceptions=False
    ) as client:
        response = client.get(
            PATH,
            params={"operationId": seed.reservation.operation_id.value},
            headers={"Authorization": "Bearer " + token},
        )
    assert response.status_code == (403 if change in ("suspended", "recovery") else 401), (
        response.text
    )
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("unavailable", ["hydra", "kratos"])
async def test_real_registered_route_preserves_provider_unavailability(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
    unavailable: Literal["hydra", "kratos"],
) -> None:
    seed = await _history(database, human)
    tokens = await provider.issue_tokens(human, credential_binding=_binding(seed))
    with TestClient(
        create_app(_settings(temporary_postgres_settings, unavailable=unavailable)),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            PATH,
            params={"operationId": seed.reservation.operation_id.value},
            headers={"Authorization": f"Bearer {tokens.access_token.value}"},
        )
    assert response.status_code == 503, response.text
    assert response.headers["cache-control"] == "no-store"
