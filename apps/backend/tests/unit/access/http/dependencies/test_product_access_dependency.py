from typing import Annotated, override
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers

KEY = "ifm_app_00000000-0000-4000-8000-000000000001_" + "A" * 43
APP = AccessContextDTO(PrincipalId(UUID(int=11)), MockAuthenticationEvidence.application_key())
HUMAN = AccessContextDTO(PrincipalId(UUID(int=12)), MockAuthenticationEvidence.browser())


class MockCookie(HumanSessionAuthenticator):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        self.calls += 1
        return HUMAN


class MockBearer(HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        self.calls += 1
        return HUMAN


def application(
    app_auth: MockApplicationAuthenticator, cookie: MockCookie, bearer: MockBearer
) -> FastAPI:
    result = FastAPI(debug=False)
    register_error_handlers(result)
    dependency = ProductAccessDependency(
        cookie,
        CSRFProtectionDependency(()),
        access_token_authenticator=bearer,
        application_authenticator=app_auth,
    )

    @result.api_route("/protected", methods=["GET", "POST"])
    async def protected(access: Annotated[AccessContextDTO, Depends(dependency)]) -> dict[str, str]:
        return {"principalId": str(access.actor_principal_id.value)}

    return result


def test_application_key_never_uses_a_human_verifier_or_cookie_csrf() -> None:
    app_auth, cookie, bearer = MockApplicationAuthenticator(APP), MockCookie(), MockBearer()
    with TestClient(application(app_auth, cookie, bearer)) as client:
        response = client.post("/protected", headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == 200 and response.json() == {
        "principalId": str(APP.actor_principal_id.value)
    }
    assert app_auth.calls == 1 and cookie.calls == bearer.calls == 0


def test_rejected_key_has_no_human_fallback() -> None:
    app_auth, cookie, bearer = MockApplicationAuthenticator(APP), MockCookie(), MockBearer()
    app_auth.failure = AuthenticationRequiredError()
    with TestClient(application(app_auth, cookie, bearer)) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == 401
    assert response.headers["www-authenticate"].endswith('error="invalid_token"')
    assert cookie.calls == bearer.calls == 0


def test_unavailable_key_verification_is_503_without_fallback() -> None:
    app_auth, cookie, bearer = MockApplicationAuthenticator(APP), MockCookie(), MockBearer()
    app_auth.failure = DependencyUnavailableError()
    with TestClient(application(app_auth, cookie, bearer)) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == 503
    assert cookie.calls == bearer.calls == 0


def test_competing_credentials_stop_all_verification() -> None:
    app_auth, cookie, bearer = MockApplicationAuthenticator(APP), MockCookie(), MockBearer()
    with TestClient(application(app_auth, cookie, bearer)) as client:
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer " + KEY, "Cookie": "ory_kratos_session=cookie"},
        )
    assert response.status_code == 400
    assert app_auth.calls == cookie.calls == bearer.calls == 0


def test_existing_cookie_and_human_bearer_paths_remain_separate() -> None:
    app_auth, cookie, bearer = MockApplicationAuthenticator(APP), MockCookie(), MockBearer()
    with TestClient(application(app_auth, cookie, bearer)) as client:
        assert (
            client.get("/protected", headers={"Cookie": "ory_kratos_session=cookie"}).status_code
            == 200
        )
        assert (
            client.post("/protected", headers={"Cookie": "ory_kratos_session=cookie"}).status_code
            == 403
        )
        assert (
            client.post("/protected", headers={"Authorization": "Bearer human"}).status_code == 200
        )
    assert cookie.calls == 2 and bearer.calls == 1 and app_auth.calls == 0
