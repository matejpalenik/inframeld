from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from json import dumps
from uuid import UUID

import pytest
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
from tests.unit.access.http.routes.test_application_account_routes import MockAccountAuthenticator
from tests.unit.indexing.application.services.test_embedding_profile_creation_service import (
    MockEmbeddingProfileCreationRepository,
)
from tests.unit.indexing.application.services.test_embedding_profile_read_service import (
    MockEmbeddingProfileReadRepository,
)

from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.indexing.application.services.embedding_profile_creation_service import (
    EmbeddingProfileCreationService,
)
from inframeld_backend.indexing.application.services.embedding_profile_read_service import (
    EmbeddingProfileReadService,
)
from inframeld_backend.indexing.http.routes.embedding_profile_routes import (
    create_embedding_profile_router,
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
from inframeld_backend.shared.infrastructure.resources.openai_embedding_tokenizer import (
    OpenAIEmbeddingTokenizer,
)

ROUTE = f"/v1/projects/{PROJECT_ID.value}/embedding-profiles"
HEADERS = {"Authorization": "Bearer human-access-token", "Idempotency-Key": "profile-create"}
DEFINITION: dict[str, str | int] = {
    "modelConnectionId": str(UUID(int=4)),
    "model": "text-embedding-3-small",
    "dimensions": 1536,
    "normalization": "l2",
    "distance": "cosine",
    "documentPrefix": "  passage: é\n",
    "queryPrefix": " query: ",
    "contextTokens": 8191,
}
BODY = {"name": "support-embeddings", "displayName": "Support embeddings", "definition": DEFINITION}


def _client(events: list[str]) -> TestClient:
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION

    @asynccontextmanager
    async def open_creator() -> AsyncGenerator[EmbeddingProfileCreationService]:
        yield EmbeddingProfileCreationService(
            MockEmbeddingProfileCreationRepository(events),
            idempotency,
            RequestFingerprintService(RequestFingerprintKey(b"E" * 32)),
            transactions=MockTransactions(events),
            official_destinations=ModelConnectionDestinationPolicy(
                https_base_urls=frozenset({"https://api.openai.com/v1"})
            ),
        )

    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[EmbeddingProfileReadService]:
        yield EmbeddingProfileReadService(
            MockTransactions(events), MockEmbeddingProfileReadRepository(events)
        )

    auth = MockAccountAuthenticator()
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(
        create_embedding_profile_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(
                    ACCESS, failure=AuthenticationRequiredError()
                ),
            ),
            open_creator,
            open_reader,
            OpenAIEmbeddingTokenizer.token_bound,
        )
    )
    return TestClient(app)


def test_create_preserves_effective_recipe_and_exact_initial_grants() -> None:
    with _client([]) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    profile = result["profile"]
    definition = profile["definition"]
    assert {field: definition[field] for field in DEFINITION} == DEFINITION
    assert definition["expectedProvider"] == "openai"
    assert definition["expectedModelRevision"] is None
    assert definition["tokenBound"] == {
        "kind": "exact",
        "implementation": "tiktoken/cl100k_base",
        "revision": OpenAIEmbeddingTokenizer.token_bound.revision,
    }
    assert profile["shardCount"] == 2
    assert result["projectAccessRevision"] == 8
    assert result["initialGrants"] == [
        {
            "target": {
                "kind": "embedding-profile",
                "embeddingProfileId": profile["embeddingProfileId"],
            },
            "actionId": action,
            "canGrant": True,
        }
        for action in ("view-embedding-profile", "use-embedding-profile")
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("documentPrefix", "embedded\0null"),
        ("queryPrefix", "\ud800"),
        ("dimensions", "1536"),
        ("contextTokens", 8192),
        ("tokenBound", "caller-chosen"),
    ],
)
def test_invalid_definition_stops_before_persistence(field: str, value: str | int) -> None:
    events: list[str] = []
    body = dumps({**BODY, "definition": {**DEFINITION, field: value}})
    with _client(events) as client:
        response = client.post(
            ROUTE, content=body, headers={**HEADERS, "Content-Type": "application/json"}
        )

    assert response.status_code == 422
    assert not events


def test_currently_visible_list_and_exact_detail_use_same_wire_shape() -> None:
    with _client([]) as client:
        page = client.get(f"{ROUTE}?limit=1", headers=HEADERS)
        detail = client.get(f"{ROUTE}/{UUID(int=4)}", headers=HEADERS)

    assert page.status_code == detail.status_code == 200
    assert page.headers["cache-control"] == detail.headers["cache-control"] == "no-store"
    assert page.json()["items"] == [detail.json()]
    assert page.json()["nextCursor"] is not None


def test_create_uses_the_existing_json_envelope_and_browser_csrf() -> None:
    events: list[str] = []
    with _client(events) as client:
        oversized = client.post(
            ROUTE,
            json={**BODY, "definition": {**DEFINITION, "documentPrefix": "a" * 32_768}},
            headers=HEADERS,
        )
        cross_site = client.post(
            ROUTE,
            json=BODY,
            headers={
                "Idempotency-Key": "profile-create",
                "Cookie": "ory_kratos_session=controlled-cookie",
                "Origin": "https://other.test",
            },
        )
    assert oversized.status_code == 413
    assert cross_site.status_code == 403
    assert not events
