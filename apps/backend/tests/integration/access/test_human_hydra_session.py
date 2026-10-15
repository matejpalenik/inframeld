"""Verify real Hydra tokens through the backend's complete human authentication path."""

import os
from collections.abc import AsyncGenerator
from typing import Literal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import update
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.hydra_provider import (
    API_AUDIENCE,
    HYDRA_ISSUER,
    HydraTestProvider,
    hydra_test_provider,
)
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_admin import disable_identity
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)


@pytest_asyncio.fixture
async def provider() -> AsyncGenerator[HydraTestProvider]:
    async with hydra_test_provider() as provider:
        yield provider


@pytest_asyncio.fixture
async def human(provider: HydraTestProvider) -> RegisteredHumanDTO:
    async with create_browser(public_url=KRATOS_PUBLIC_URL) as browser:
        return await register_human(browser)


async def _admit_human(database: Database, human: RegisteredHumanDTO) -> Principal:
    async with database.session() as session, session.begin():
        return await MockAccessScenarios.seed_linked_human(
            session,
            VerifiedHumanIdentityDTO(AUTHORITY, human.subject),
        )


def _application_settings(
    database_settings: DatabaseSettings,
    *,
    unavailable: Literal["hydra", "kratos"] | None = None,
) -> ApplicationSettings:
    return get_settings().model_copy(
        update={
            "database": database_settings,
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


@pytest.mark.asyncio
async def test_real_cookie_and_access_token_resolve_the_same_local_human(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
) -> None:
    """Real provider verification must converge on the one existing local principal."""
    principal = await _admit_human(database, human)
    tokens = await provider.issue_tokens(human)
    application = create_app(_application_settings(temporary_postgres_settings))

    with TestClient(application, raise_server_exceptions=False) as client:
        bearer = client.get(
            "/v1/session",
            headers={"Authorization": f"Bearer {tokens.access_token.value}"},
        )
        assert bearer.status_code == 200, bearer.text
        assert bearer.json() == {"principalId": str(principal.id.value)}

        client.cookies.set("ory_kratos_session", human.credential.value)
        cookie = client.get("/v1/session")
        assert cookie.status_code == 200, cookie.text
        assert cookie.json() == bearer.json()


@pytest.mark.asyncio
async def test_real_token_without_local_admission_is_denied(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
) -> None:
    """A real Hydra login does not create or admit a local Inframeld account."""
    tokens = await provider.issue_tokens(human)

    with TestClient(
        create_app(_application_settings(temporary_postgres_settings)),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/v1/session",
            headers={"Authorization": f"Bearer {tokens.access_token.value}"},
        )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "access_denied"


@pytest.mark.asyncio
async def test_real_token_rechecks_local_suspension(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
) -> None:
    """A still-valid provider token cannot bypass a later local suspension."""
    principal = await _admit_human(database, human)
    tokens = await provider.issue_tokens(human)
    headers = {"Authorization": f"Bearer {tokens.access_token.value}"}

    with TestClient(
        create_app(_application_settings(temporary_postgres_settings)),
        raise_server_exceptions=False,
    ) as client:
        assert client.get("/v1/session", headers=headers).status_code == 200

        async with database.session() as session, session.begin():
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == principal.id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )

        response = client.get("/v1/session", headers=headers)

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoke-token", "disable-identity"])
async def test_real_provider_changes_stop_the_next_request(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
    change: Literal["revoke-token", "disable-identity"],
) -> None:
    """Each request must observe token revocation and current Kratos eligibility."""
    await _admit_human(database, human)
    tokens = await provider.issue_tokens(human)
    headers = {"Authorization": f"Bearer {tokens.access_token.value}"}

    with TestClient(
        create_app(_application_settings(temporary_postgres_settings)),
        raise_server_exceptions=False,
    ) as client:
        assert client.get("/v1/session", headers=headers).status_code == 200
        if change == "revoke-token":
            await provider.revoke_access_token(tokens.access_token)
        else:
            await disable_identity(human.subject)

        response = client.get("/v1/session", headers=headers)

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("credential_kind", ["refresh-token", "missing-api-audience"])
async def test_real_wrong_token_kind_or_audience_is_rejected(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
    credential_kind: Literal["refresh-token", "missing-api-audience"],
) -> None:
    """A real refresh token or an access token without this API's audience cannot authenticate."""
    await _admit_human(database, human)
    tokens = await provider.issue_tokens(
        human, include_audience=credential_kind != "missing-api-audience"
    )
    credential = (
        tokens.refresh_token.get_secret_value()
        if credential_kind == "refresh-token"
        else tokens.access_token.value
    )

    with TestClient(
        create_app(_application_settings(temporary_postgres_settings)),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/v1/session",
            headers={"Authorization": f"Bearer {credential}"},
        )

    assert response.status_code == 401, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ["hydra", "kratos"])
async def test_real_provider_connection_failures_return_503(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    provider: HydraTestProvider,
    human: RegisteredHumanDTO,
    unavailable: Literal["hydra", "kratos"],
) -> None:
    """Exercise each SDK's transport failure without stopping shared test services."""
    await _admit_human(database, human)
    tokens = await provider.issue_tokens(human)

    with TestClient(
        create_app(_application_settings(temporary_postgres_settings, unavailable=unavailable)),
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/v1/session",
            headers={"Authorization": f"Bearer {tokens.access_token.value}"},
        )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "dependency_unavailable"
