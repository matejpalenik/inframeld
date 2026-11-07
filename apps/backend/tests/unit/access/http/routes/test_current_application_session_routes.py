from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_application_session_reader import MockApplicationSessionReader

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.application_key_dependency import (
    ApplicationKeyDependency,
)
from inframeld_backend.access.http.handlers.application_key_credential_error_handler import (
    register_application_key_credential_error_handler,
)
from inframeld_backend.access.http.routes.current_application_session_routes import (
    create_application_session_router,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

PRINCIPAL = PrincipalId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
KEY = "ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43


def application(reader: MockApplicationSessionReader) -> FastAPI:
    app = FastAPI(debug=False)
    register_error_handlers(app)
    register_application_key_credential_error_handler(app)
    app.add_middleware(RequestContextMiddleware)
    auth = MockApplicationAuthenticator(
        AccessContextDTO(PRINCIPAL, MockAuthenticationEvidence.application_key())
    )
    app.include_router(create_application_session_router(ApplicationKeyDependency(auth), reader))
    return app


def test_session_response_has_exact_safe_identity_and_no_store() -> None:
    reader = MockApplicationSessionReader(CurrentApplicationSessionDTO(PRINCIPAL, PROJECT))
    with TestClient(application(reader)) as client:
        response = client.get("/v1/application-session", headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == 200
    assert response.json() == {"principalId": str(PRINCIPAL.value), "projectId": str(PROJECT.value)}
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])


def test_unsupported_human_bearer_never_reads_application_identity() -> None:
    reader = MockApplicationSessionReader(CurrentApplicationSessionDTO(PRINCIPAL, PROJECT))
    with TestClient(application(reader)) as client:
        response = client.get(
            "/v1/application-session", headers={"Authorization": "Bearer human-opaque"}
        )
    assert response.status_code == 401 and reader.calls == 0


def test_key_rejected_at_disclosure_gets_safe_bearer_challenge() -> None:
    reader = MockApplicationSessionReader(CurrentApplicationSessionDTO(PRINCIPAL, PROJECT))
    reader.failure = ApplicationKeyCredentialRejectedError()
    with TestClient(application(reader), raise_server_exceptions=False) as client:
        response = client.get("/v1/application-session", headers={"Authorization": "Bearer " + KEY})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert response.json()["code"] == "http_error"
    assert KEY not in response.text
