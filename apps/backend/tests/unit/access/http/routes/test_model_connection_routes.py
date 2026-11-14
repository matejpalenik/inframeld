from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    PROJECT_ID,
    MockOperationIdempotency,
    MockTransactions,
)
from tests.unit.access.application.services.test_model_connection_creation_service import (
    COMMAND,
    MockCreationRepository,
)
from tests.unit.access.application.services.test_model_connection_read_service import (
    FIRST,
    MockReadRepository,
)
from tests.unit.access.http.routes.test_application_account_routes import MockAccountAuthenticator

from inframeld_backend.access.application.services.model_connection_creation_service import (
    ModelConnectionCreationService,
)
from inframeld_backend.access.application.services.model_connection_read_service import (
    ModelConnectionReadService,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.model_connection_routes import (
    create_model_connection_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

ROUTE = f"/v1/projects/{PROJECT_ID.value}/model-connections"
BODY = {
    "name": "company-gateway",
    "displayName": "Company gateway",
    "access": {
        "provider": "openai-compatible",
        "baseUrl": COMMAND.access.base_url,
        "apiVersion": None,
        "authentication": "api-key",
    },
}
HEADERS = {"Authorization": "Bearer human-access-token", "Idempotency-Key": "original"}


def _client(events: list[str]) -> TestClient:
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION

    @asynccontextmanager
    async def open_creator() -> AsyncGenerator[ModelConnectionCreationService]:
        yield ModelConnectionCreationService(
            MockTransactions(events),
            MockCreationRepository(events),
            idempotency,
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
            ModelConnectionDestinationPolicy(https_base_urls=frozenset({COMMAND.access.base_url})),
        )

    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ModelConnectionReadService]:
        yield ModelConnectionReadService(MockTransactions(events), MockReadRepository(events))

    auth = MockAccountAuthenticator()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_model_connection_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(
                    ACCESS,
                    failure=AuthenticationRequiredError(),
                ),
            ),
            open_creator,
            open_reader,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


def test_create_returns_safe_exact_receipt_and_usage_returns_empty_page() -> None:
    with _client([]) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
        usage = client.get(f"{ROUTE}/{FIRST.connection_id.value}/usage", headers=HEADERS)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["projectAccessRevision"] == 8
    assert result["connection"]["access"] == BODY["access"]
    assert result["connection"]["credential"] == {"present": False, "revision": 0}
    assert result["initialGrants"] == [
        {
            "target": {
                "kind": "model-connection",
                "modelConnectionId": result["connection"]["modelConnectionId"],
            },
            "actionId": action.value,
            "canGrant": True,
        }
        for action in ModelConnectionAction
    ]
    assert usage.status_code == 200 and usage.json() == {"items": [], "nextCursor": None}


def test_reject_duplicate_inputs_and_credentials_without_invoking_creation() -> None:
    events: list[str] = []
    with _client(events) as client:
        ambiguous = client.post(
            ROUTE,
            content='{"name":"first","name":"second"}',
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        unknown = client.post(
            ROUTE, json={**BODY, "credential": "never-disclose-this"}, headers=HEADERS
        )
        duplicate = client.get(f"{ROUTE}?limit=1&limit=2", headers=HEADERS)
        unknown_query = client.get(f"{ROUTE}/{FIRST.connection_id.value}?limit=1", headers=HEADERS)
    assert all(
        r.status_code == 422 and r.json()["code"] == "invalid_input"
        for r in (ambiguous, duplicate, unknown_query)
    )
    assert unknown.status_code == 422
    assert "never-disclose-this" not in unknown.text
    assert all(
        r.headers["cache-control"] == "no-store"
        for r in (ambiguous, unknown, duplicate, unknown_query)
    )
    assert not events
