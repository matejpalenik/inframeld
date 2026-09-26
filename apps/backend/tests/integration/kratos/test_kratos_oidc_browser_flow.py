"""Verify that mock OIDC login creates a Kratos session without granting local access."""

import os

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.access_scenarios import seed_linked_human, seed_project_authorization
from tests.support.kratos_browser import (
    KRATOS_PUBLIC_URL,
    WhoamiResponse,
    begin_oidc_login,
    create_browser,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1"
    or os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires PostgreSQL, Kratos, and the mock OIDC provider",
)


@pytest.mark.asyncio
async def test_oidc_session_needs_exact_local_link_and_stored_action_grant(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Complete OIDC login, then check identity admission and project authority."""
    async with create_browser() as browser:
        authorization_url = httpx2.URL(await begin_oidc_login(browser))
        assert authorization_url.host == "mock-oidc"
        assert authorization_url.port == 8080

        # The host-run test reaches the Compose provider through its published port.
        public_url = authorization_url.copy_with(host="127.0.0.1", port=15556)
        async with httpx2.AsyncClient(
            follow_redirects=False,
            timeout=15.0,
            trust_env=False,
        ) as upstream_browser:
            authorized = await upstream_browser.get(
                public_url,
                headers={"Host": "mock-oidc:8080"},
            )

        assert authorized.status_code in {302, 303}, authorized.text
        callback_url = authorized.headers["location"]
        assert callback_url.startswith(
            "http://127.0.0.1:14433/self-service/methods/oidc/callback/company"
        )

        # Use the original browser: it holds Kratos's login-flow and CSRF cookies.
        completed = await browser.get(callback_url, headers={"Accept": "text/html"})
        assert completed.status_code in {302, 303}, completed.text

        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == 200, whoami.text
        identity = WhoamiResponse.model_validate_json(whoami.text)
        subject = IdentitySubject(str(identity.identity.id))

        cookie = browser.cookies.get("ory_kratos_session")
        assert cookie is not None

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
        client.cookies.set("ory_kratos_session", cookie)

        # Kratos knows the person, but Inframeld has not admitted them.
        assert client.get("/v1/session").status_code == 403

        # The same subject under another authority must not match.
        async with database.session() as session, session.begin():
            await seed_linked_human(
                session,
                VerifiedHumanIdentityDTO(
                    IdentityAuthority("kratos:another-installation"),
                    subject,
                ),
            )
        assert client.get("/v1/session").status_code == 403

        # Admit the exact verified pair to a project, without an action grant.
        async with database.session() as session, session.begin():
            scenario = await seed_project_authorization(
                session,
                is_project_member=True,
                has_action_grant=False,
            )
            principal_row = await session.get(PrincipalRow, scenario.principal_id.value)
            assert principal_row is not None
            session.add(
                HumanIdentityLinkRow(
                    authority=AUTHORITY.value,
                    subject=subject.value,
                    organization_id=principal_row.organization_id,
                    principal_id=scenario.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )

        admitted = client.get("/v1/session")
        assert admitted.status_code == 200, admitted.text
        assert admitted.json() == {
            "principalId": str(scenario.principal_id.value),
        }

    # The mock ID token contains groups=["administrators"]. That claim has
    # created no Inframeld action grant.
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))
        with pytest.raises(AccessDeniedError):
            await authorizer.require_action(
                access=AccessContextDTO(actor_principal_id=scenario.principal_id),
                action=scenario.action,
                target=ProjectActionTargetDTO(project_id=scenario.project_id),
            )
