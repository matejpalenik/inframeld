from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_invitation_session_verifier import MockInvitationSessionVerifier

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
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.invitation_browser_dependency import (
    InvitationBrowserDependency,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers

PROOF = InvitationBrowserProofDTO(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject(str(UUID(int=1)))),
    None,
)
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
}


def client_for(
    verifier: MockInvitationSessionVerifier | None, *, observe: bool = False
) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    dependency = InvitationBrowserDependency(
        verifier,
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
        observe_password_completion=observe,
    )

    @app.post("/recipient")
    async def recipient(
        proof: Annotated[InvitationBrowserProofDTO, Depends(dependency)],
    ) -> dict[str, bool]:
        assert proof == PROOF
        return {"verified": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("observe", [False, True])
def test_unadmitted_browser_uses_exact_observation_profile(observe: bool) -> None:
    verifier = MockInvitationSessionVerifier(PROOF)
    with client_for(verifier, observe=observe) as client:
        response = client.post("/recipient", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"verified": True}
    assert verifier.calls == [(BrowserSessionCredential("controlled-cookie"), observe)]


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"Authorization": "Bearer human-token"}, 401),
        ({"Authorization": "Bearer ifm_app_00000000-0000-4000-8000-000000000001_" + "A" * 43}, 401),
        ({**HEADERS, "Authorization": "Bearer human-token"}, 400),
        ([("Authorization", "Bearer first"), ("Authorization", "Bearer second")], 400),
        ({**HEADERS, "X-Inframeld-CSRF": "0"}, 403),
        ({**HEADERS, "Origin": "https://foreign.test"}, 403),
    ],
)
def test_unsupported_or_unprotected_input_never_contacts_provider(
    headers: dict[str, str] | list[tuple[str, str]], status: int
) -> None:
    verifier = MockInvitationSessionVerifier(PROOF)
    with client_for(verifier) as client:
        response = client.post("/recipient", headers=headers)
    assert response.status_code == status
    assert verifier.calls == []
    assert "controlled-cookie" not in response.text


def test_rejected_cookie_is_unauthorized() -> None:
    verifier = MockInvitationSessionVerifier(None)
    with client_for(verifier) as client:
        response = client.post("/recipient", headers=HEADERS)
    assert response.status_code == 401
    assert len(verifier.calls) == 1


@pytest.mark.parametrize("configured", [False, True])
def test_required_provider_unavailable_is_safe_503(configured: bool) -> None:
    verifier = MockInvitationSessionVerifier(PROOF) if configured else None
    if verifier is not None:
        verifier.error = DependencyUnavailableError()
    with client_for(verifier) as client:
        response = client.post("/recipient", headers=HEADERS)
    assert response.status_code == 503
    assert "controlled-cookie" not in response.text
