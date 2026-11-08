"""Qualify password enrollment independently of the current browser login method."""

import os
from uuid import uuid4

import httpx2
import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.models.session import Session
from pydantic import SecretStr
from tests.support.integration_services import KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL, MOCK_OIDC_URL
from tests.support.kratos_admin import get_identity
from tests.support.kratos_browser import (
    begin_oidc_login,
    create_browser,
    login_human,
    register_human,
    submit_password_login,
)
from tests.support.kratos_settings import SettingsFlowResponse, submit_password_settings

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.verifiers.kratos_invitation_session_verifier import (
    KratosInvitationSessionVerifier,
)

AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the maintained Kratos and mock OIDC integration services",
)


async def _verify(credential: BrowserSessionCredential) -> InvitationBrowserProofDTO | None:
    client = ApiClient(Configuration(host=KRATOS_PUBLIC_URL))
    admin = ApiClient(Configuration(host=KRATOS_ADMIN_URL))
    try:
        return await KratosInvitationSessionVerifier(
            FrontendApi(client), AUTHORITY, identity_client=IdentityApi(admin)
        ).verify(credential, observe_password_completion=True)
    finally:
        client.rest_client.pool_manager.clear()
        admin.rest_client.pool_manager.clear()


async def _oidc_login(
    browser: httpx2.AsyncClient,
) -> tuple[BrowserSessionCredential, Session]:
    """Complete the existing mock-provider flow with the browser's original CSRF state."""
    authorization_url = httpx2.URL(await begin_oidc_login(browser))
    assert authorization_url.host == httpx2.URL(MOCK_OIDC_URL).host
    assert authorization_url.port == httpx2.URL(MOCK_OIDC_URL).port

    async with httpx2.AsyncClient(
        follow_redirects=False, timeout=15.0, trust_env=False
    ) as upstream_browser:
        authorized = await upstream_browser.get(authorization_url)
    assert authorized.status_code in {302, 303}

    callback_url = authorized.headers["location"]
    assert callback_url.startswith(
        f"{KRATOS_PUBLIC_URL}/self-service/methods/oidc/callback/company"
    )
    completed = await browser.get(callback_url, headers={"Accept": "text/html"})
    assert completed.status_code in {302, 303}

    whoami = await browser.get("/sessions/whoami")
    assert whoami.status_code == 200
    cookie = browser.cookies.get("ory_kratos_session")
    assert cookie is not None

    return BrowserSessionCredential(cookie), Session.model_validate_json(whoami.text)


@pytest.mark.asyncio
async def test_password_registration_and_login_prove_exact_recipient_completion() -> None:
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)
        registered = await _verify(human.credential)

    assert registered == InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=human.subject),
        password_completed=True,
    )

    async with create_browser() as browser:
        credential = await login_human(browser, human)
        authenticated = await _verify(credential)

    assert authenticated == registered


@pytest.mark.asyncio
async def test_never_password_enrolled_oidc_identity_has_no_completion() -> None:
    async with create_browser() as browser:
        credential, session = await _oidc_login(browser)
        assert session.identity is not None
        subject = IdentitySubject(str(session.identity.id))
        identity = await get_identity(subject)
        assert str(identity.id) == subject.value
        assert session.authentication_methods
        assert {method.method for method in session.authentication_methods} == {"oidc"}

        proof = await _verify(credential)

    assert proof == InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=subject),
        password_completed=False,
    )


@pytest.mark.asyncio
async def test_password_enrolled_identity_keeps_eligible_oidc_only_session() -> None:
    """Native password completion does not require replacing the verified OIDC login."""
    async with create_browser() as browser:
        credential, original_session = await _oidc_login(browser)
        assert original_session.identity is not None
        subject = IdentitySubject(str(original_session.identity.id))
        assert original_session.authentication_methods
        assert {method.method for method in original_session.authentication_methods} == {"oidc"}
        assert (await _verify(credential)) == InvitationBrowserProofDTO(
            identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=subject),
            password_completed=False,
        )

        started = await browser.get(
            "/self-service/settings/browser", headers={"Accept": "application/json"}
        )
        assert started.status_code == 200
        settings = SettingsFlowResponse.model_validate_json(started.text)
        assert str(settings.identity.id) == subject.value
        password = SecretStr(f"TestPassphrase-{uuid4().hex}!")
        saved = await submit_password_settings(browser, settings, password)
        assert saved.status_code in {200, 303}

        persisted = await get_identity(subject)
        assert persisted.credentials is not None and "password" in persisted.credentials
        assert persisted.traits is not None
        email: object = persisted.traits.get("email")
        assert isinstance(email, str)

        # Confirm persistence through an independent password login, not a settings page.
        async with create_browser() as password_browser:
            logged_in = await submit_password_login(
                password_browser, email=email, password=password
            )
            assert logged_in.status_code in {200, 303}
            password_session_response = await password_browser.get("/sessions/whoami")
            assert password_session_response.status_code == 200
            password_session = Session.model_validate_json(password_session_response.text)
            assert password_session.identity is not None
            assert str(password_session.identity.id) == subject.value

        # Observe the original saved credential, not the password browser's new cookie.
        current = await browser.get(
            "/sessions/whoami",
            headers={"Cookie": f"ory_kratos_session={credential.value}"},
        )
        assert current.status_code == 200
        session = Session.model_validate_json(current.text)
        assert session.active is True and session.identity is not None
        assert session.id == original_session.id
        assert str(session.identity.id) == subject.value
        assert session.authentication_methods
        assert {method.method for method in session.authentication_methods} == {"oidc"}

        proof = await _verify(credential)

    assert proof == InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=subject),
        password_completed=True,
    )
