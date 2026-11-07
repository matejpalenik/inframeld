from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.http.handlers.application_key_credential_error_handler import (
    register_application_key_credential_error_handler,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers


def test_current_key_rejection_retains_generic_problem_and_constant_challenge() -> None:
    app = FastAPI()
    register_error_handlers(app)
    register_application_key_credential_error_handler(app)

    @app.get("/protected")
    async def protected() -> None:
        raise ApplicationKeyCredentialRejectedError()

    with TestClient(app) as client:
        response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == "http_error"
