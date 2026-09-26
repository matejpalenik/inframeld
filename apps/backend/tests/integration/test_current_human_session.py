"""Verify that the real API resolves a Kratos cookie to a local human."""

import os
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from inframeld_backend.access.domain.values import (
    IdentityAuthority,
    IdentitySubject,
    OrganizationId,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
)
from inframeld_backend.access.infrastructure.persistence_models import (
    HumanIdentityLinkRow,
    OrganizationRow,
    PrincipalRow,
)
from inframeld_backend.composition import create_app
from inframeld_backend.shared.infrastructure.database import Database
from inframeld_backend.shared.infrastructure.settings import (
    DatabaseSettings,
    KratosSettings,
    get_settings,
)

KRATOS_PUBLIC_URL = "http://127.0.0.1:14433"
AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1"
    or os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the PostgreSQL and Kratos integration services",
)


async def _register_kratos_human() -> tuple[IdentitySubject, str]:
    """Register a unique identity and return its subject and browser cookie."""
    async with httpx2.AsyncClient(
        base_url=KRATOS_PUBLIC_URL,
        follow_redirects=False,
        timeout=15.0,
        trust_env=False,
    ) as browser:
        started = await browser.get(
            "/self-service/registration/browser",
            headers={"Accept": "application/json"},
        )
        assert started.status_code == 200, started.text

        flow = started.json()
        csrf_token = next(
            node["attributes"]["value"]
            for node in flow["ui"]["nodes"]
            if node["attributes"]["name"] == "csrf_token"
        )

        completed = await browser.post(
            flow["ui"]["action"],
            data={
                "csrf_token": csrf_token,
                "traits.email": f"session-{uuid4().hex}@example.test",
                "password": f"TestPassphrase-{uuid4().hex}!",
                "method": "password",
            },
            headers={"Accept": "application/json"},
        )
        assert completed.status_code in {200, 303}, completed.text

        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == 200, whoami.text

        identity_id = whoami.json()["identity"]["id"]
        cookie = browser.cookies.get("ory_kratos_session")
        assert isinstance(identity_id, str)
        assert isinstance(cookie, str)

        return IdentitySubject(str(UUID(identity_id))), cookie


@pytest.mark.asyncio
async def test_current_session_uses_kratos_cookie_and_local_identity_link(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Return the active local principal linked to a real Kratos session."""
    subject, cookie = await _register_kratos_human()
    organization_id = OrganizationId(uuid4())
    principal_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        session.add(OrganizationRow(id=organization_id, name="Session test"))
        await session.flush()

        session.add(
            PrincipalRow(
                id=principal_id,
                organization_id=organization_id,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Session test human",
            )
        )
        await session.flush()

        session.add(
            HumanIdentityLinkRow(
                authority=AUTHORITY.value,
                subject=subject.value,
                organization_id=organization_id,
                principal_id=principal_id,
                principal_kind=PrincipalKind.HUMAN,
            )
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
        assert response.json() == {"principalId": str(principal_id)}

        client.cookies.clear()
        assert client.get("/v1/session").status_code == 401
