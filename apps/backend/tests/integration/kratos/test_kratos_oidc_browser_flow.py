"""Verify that mock OIDC login creates a Kratos session without granting local access."""

import asyncio
import os
import subprocess
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient
from ory_kratos_client.models.identity import Identity as KratosIdentity
from pydantic import HttpUrl
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.kratos_browser import (
    KRATOS_PUBLIC_URL,
    BrowserFlow,
    RegisteredHumanDTO,
    WhoamiResponse,
    begin_oidc_login,
    create_browser,
    login_human,
    register_human,
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
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1"
    or os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires PostgreSQL, Kratos, and the mock OIDC provider",
)


async def _matching_email_challenge(
    oidc_browser: httpx2.AsyncClient,
    password_browser: httpx2.AsyncClient,
) -> tuple[BrowserFlow, RegisteredHumanDTO, str]:
    """Start OIDC with the email of a separately registered password account."""
    authorization_url = httpx2.URL(await begin_oidc_login(oidc_browser))
    assert authorization_url.host == "mock-oidc"
    assert authorization_url.port == 8080

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

    callback_url = httpx2.URL(authorized.headers["location"])
    code = callback_url.params.get("code")
    assert code is not None

    # The mock provider derives its subject and email from the authorization code.
    human = await register_human(
        password_browser,
        email=f"oidc-{code}@example.test",
    )

    completed = await oidc_browser.get(
        str(callback_url),
        headers={"Accept": "text/html"},
    )
    assert completed.status_code in {302, 303}, completed.text

    redirect = httpx2.URL(completed.headers["location"])
    assert redirect.path == "/login", redirect.path
    flow_id = redirect.params.get("flow")
    assert flow_id is not None

    challenge = await oidc_browser.get(
        "/self-service/login/flows",
        params={"id": flow_id},
        headers={"Accept": "application/json"},
    )
    assert challenge.status_code == 200, challenge.text

    flow = BrowserFlow.model_validate_json(challenge.text)
    assert any(node.attributes.name == "password" for node in flow.ui.nodes)
    return flow, human, code


async def _get_test_kratos_identity(subject: IdentitySubject) -> KratosIdentity:
    """Read credential identifiers without publishing the test admin port."""
    result = await asyncio.to_thread(
        subprocess.run,
        [
            str(REPOSITORY_ROOT / "scripts/dev-compose.sh"),
            "test-kratos-get-identity",
            subject.value,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return KratosIdentity.model_validate_json(result.stdout)


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

        redirect = httpx2.URL(completed.headers["location"])
        assert browser.cookies.get("ory_kratos_session") is not None, (
            f"Kratos redirected to {redirect.path}; query keys={list(redirect.params.keys())}"
        )

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
            await MockAccessScenarios.seed_linked_human(
                session,
                VerifiedHumanIdentityDTO(
                    IdentityAuthority("kratos:another-installation"),
                    subject,
                ),
            )
        assert client.get("/v1/session").status_code == 403

        # Admit the exact verified pair to a project, without an action grant.
        async with database.session() as session, session.begin():
            scenario = await MockAccessScenarios.seed_project_authorization(
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
                action_id=scenario.action,
                target=ProjectActionTargetDTO(project_id=scenario.project_id),
            )


@pytest.mark.asyncio
async def test_matching_email_does_not_silently_link_oidc() -> None:
    """A matching email alone creates neither a session nor an OIDC link."""
    async with create_browser() as oidc_browser, create_browser() as password_browser:
        _, human, _ = await _matching_email_challenge(
            oidc_browser,
            password_browser,
        )

        assert (await oidc_browser.get("/sessions/whoami")).status_code == 401

        identity = await _get_test_kratos_identity(human.subject)
        assert identity.credentials is not None
        assert "password" in identity.credentials
        assert "oidc" not in identity.credentials


@pytest.mark.asyncio
async def test_password_proof_links_oidc_to_existing_identity() -> None:
    """Password proof attaches this provider subject to the existing identity."""
    async with create_browser() as oidc_browser, create_browser() as password_browser:
        flow, human, code = await _matching_email_challenge(
            oidc_browser,
            password_browser,
        )

        csrf_node = next(node for node in flow.ui.nodes if node.attributes.name == "csrf_token")
        csrf_token = csrf_node.attributes.value
        assert isinstance(csrf_token, str)

        proved = await oidc_browser.post(
            flow.ui.action,
            data={
                "csrf_token": csrf_token,
                "identifier": human.email,
                "password": human.password,
                "method": "password",
            },
            headers={"Accept": "application/json"},
        )
        assert proved.status_code in {200, 303}, proved.text

        linked_session = await oidc_browser.get("/sessions/whoami")
        assert linked_session.status_code == 200, linked_session.text
        assert (
            str(WhoamiResponse.model_validate_json(linked_session.text).identity.id)
            == human.subject.value
        )

        identity = await _get_test_kratos_identity(human.subject)
        assert identity.id == human.subject.value
        assert identity.credentials is not None
        assert {"password", "oidc"} <= identity.credentials.keys()

        oidc_identifiers = identity.credentials["oidc"].identifiers
        assert oidc_identifiers is not None
        assert f"company:oidc-{code}" in oidc_identifiers

    # Check the password method in a fresh browser, after the link was saved.
    async with create_browser() as another_password_browser:
        await login_human(another_password_browser, human)
        password_session = await another_password_browser.get("/sessions/whoami")
        assert password_session.status_code == 200, password_session.text
        assert (
            str(WhoamiResponse.model_validate_json(password_session.text).identity.id)
            == human.subject.value
        )
