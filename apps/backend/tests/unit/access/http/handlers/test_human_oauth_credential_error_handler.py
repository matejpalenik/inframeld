from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)


def test_late_credential_rejection_preserves_generic_problem_and_bearer_challenge() -> None:
    """A transaction's rejection must tell the CLI to stop using its stale credential."""
    app = FastAPI()
    register_error_handlers(app)
    register_human_oauth_credential_error_handler(app)
    app.add_middleware(RequestContextMiddleware)

    @app.post("/_test/protected-write")
    async def protected_write() -> None:
        raise HumanOAuthCredentialRejectedError()

    with TestClient(app) as client:
        response = client.post("/_test/protected-write")
    assert response.status_code == 401
    assert response.json()["code"] == "http_error"
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert response.headers["cache-control"] == "no-store"
    assert "version" not in response.text and "recovery" not in response.text
