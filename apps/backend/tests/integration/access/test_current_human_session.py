"""Verify that the real API resolves a Kratos cookie to a local human."""

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.access_scenarios import seed_linked_human
from tests.support.kratos_browser import create_browser, register_human

from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)
from inframeld_backend.access.domain.identity_values import IdentityAuthority
from inframeld_backend.access.infrastructure.kratos.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.postgres.database import Database
from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings

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
        principal = await seed_linked_human(session, VerifiedHumanIdentity(AUTHORITY, subject))

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


@pytest.mark.parametrize("cookie", [None, "synthetic-session"])
def test_missing_kratos_configuration_returns_unavailable(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    cookie: str | None,
) -> None:
    """Keep the session route unavailable when the operator has not configured Kratos."""
    settings = get_settings().model_copy(
        update={"database": temporary_postgres_settings, "kratos": None}
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        if cookie is not None:
            client.cookies.set("ory_kratos_session", cookie)
        response = client.get("/v1/session")
    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
