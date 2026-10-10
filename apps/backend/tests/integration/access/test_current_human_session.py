"""Verify the session API's Kratos identity and failure boundaries."""

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.kratos_browser import create_browser, register_human

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

KRATOS_PUBLIC_URL = "http://127.0.0.1:14433"
AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1"
    or os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the PostgreSQL and Kratos integration services",
)


@pytest.mark.asyncio
async def test_current_session_uses_kratos_cookie_and_local_identity_link(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Return the active local principal linked to a real Kratos session."""
    async with create_browser() as browser:
        human = await register_human(browser)
    subject, cookie = human.subject, human.credential.value
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(
            session, VerifiedHumanIdentityDTO(AUTHORITY, subject)
        )

    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                authority=AUTHORITY,
            ),
        }
    )

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200

        client.cookies.set("ory_kratos_session", cookie)
        response = client.get("/v1/session")

        assert response.status_code == 200, response.text
        assert response.json() == {"principalId": str(principal.id.value)}

        client.cookies.clear()
        assert client.get("/v1/session").status_code == 401


@pytest.mark.asyncio
async def test_current_session_reports_kratos_outage(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Report a provider outage when a valid browser session cannot be verified."""
    async with create_browser() as browser:
        human = await register_human(browser)

    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://127.0.0.1:1"),
                authority=AUTHORITY,
            ),
        }
    )

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200

        client.cookies.set("ory_kratos_session", human.credential.value)
        response = client.get("/v1/session")

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "dependency_unavailable"


@pytest.mark.parametrize(
    ("cookie", "status", "code"),
    [
        (None, 401, "http_error"),
        ("synthetic-session", 503, "dependency_unavailable"),
    ],
)
def test_missing_kratos_configuration_preserves_authentication_outcomes(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    cookie: str | None,
    status: int,
    code: str,
) -> None:
    """Missing credentials need login; a supplied cookie needs configured verification."""
    settings = get_settings().model_copy(
        update={"database": temporary_postgres_settings, "kratos": None, "hydra": None}
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        if cookie is not None:
            client.cookies.set("ory_kratos_session", cookie)
        response = client.get("/v1/session")

    assert response.status_code == status
    assert response.json()["code"] == code
