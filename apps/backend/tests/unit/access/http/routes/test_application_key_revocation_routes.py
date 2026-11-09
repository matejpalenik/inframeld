"""Exercise exact Revoke transport, safe original receipts and credential protections."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.application.protocols.application_key_revoker import (
    ApplicationKeyRevoker,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.application_key_revocation_routes import (
    create_application_key_revocation_router,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

PROJECT, APP = ProjectId(UUID(int=3)), PrincipalId(UUID(int=8))
HUMAN = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
APPLICATION = AccessContextDTO(APP, MockAuthenticationEvidence.application_key())
NOW = datetime(2030, 1, 1, tzinfo=UTC)
CREDENTIAL = ApplicationKeyCredential(f"ifm_app_{UUID(int=10)}_" + "A" * 43)
ROUTE = (
    f"/v1/projects/{PROJECT.value}/application-accounts/{APP.value}/keys/"
    f"{CREDENTIAL.key_id.value}/revoke"
)
BODY = {"expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "revoke-original",
}


class MockRevoker(ApplicationKeyRevoker):
    def __init__(self, *, replay: bool = False, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[
            tuple[AccessContextDTO, RevokeApplicationKeyCommand, IdempotencyContextDTO]
        ] = []
        self.result = ApplicationKeyRevocationResultDTO(
            ApplicationKeyRevocationRecordDTO(
                operation_id=OperationId("revoked-original"),
                organization_id=OrganizationId(UUID(int=2)),
                installation_id=InstallationId(UUID(int=4)),
                actor_principal_id=HUMAN.actor_principal_id,
                access_revision=8,
                metadata=ApplicationKeyMetadataDTO(
                    CREDENTIAL.key_id,
                    APP,
                    PROJECT,
                    (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
                    NOW - timedelta(days=1),
                    NOW + timedelta(days=89),
                    NOW,
                ),
            ),
            CompletedSynchronousOperationDTO(
                OperationId("revoked-original"),
                not replay,
                OperationReplayKind.SAFE_RESULT,
                NOW + timedelta(days=1),
            ),
        )

    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyRevocationResultDTO:
        self.calls.append((access, command, context))
        if self.failure is not None:
            raise self.failure
        return self.result


class MockHumanAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.calls: list[BrowserSessionCredential | HumanAccessTokenCredential | None] = []

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        self.calls.append(credential)
        return (
            replace(HUMAN, authentication_evidence=MockAuthenticationEvidence.human_oauth())
            if isinstance(credential, HumanAccessTokenCredential)
            else HUMAN
        )


def client_for(
    revoker: MockRevoker,
    human: MockHumanAuthenticator | None = None,
    application: MockApplicationAuthenticator | None = None,
) -> TestClient:
    human = human or MockHumanAuthenticator()
    application = application or MockApplicationAuthenticator(APPLICATION)

    @asynccontextmanager
    async def open_revoker() -> AsyncGenerator[ApplicationKeyRevoker]:
        yield revoker

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_application_key_revocation_router(
            ProductAccessDependency(
                human,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=human,
                application_authenticator=application,
            ),
            open_revoker,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("replay", [False, True])
def test_revoke_returns_the_same_safe_receipt_for_first_delivery_and_replay(replay: bool) -> None:
    revoker = MockRevoker(replay=replay)
    with client_for(revoker) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"operationId", "accessRevision", "idempotencyExpiresAt", "metadata"}
    assert data["operationId"] == "revoked-original" and data["accessRevision"] == 8
    assert data["idempotencyExpiresAt"] == "2030-01-02T00:00:00Z"
    assert data["metadata"] == {
        "keyId": str(CREDENTIAL.key_id.value),
        "applicationPrincipalId": str(APP.value),
        "projectId": str(PROJECT.value),
        "prefix": "ifm_app_",
        "allowedAdapters": ["mcp", "http"],
        "createdAt": "2029-12-31T00:00:00Z",
        "expiresAt": "2030-03-31T00:00:00Z",
        "revokedAt": "2030-01-01T00:00:00Z",
    }
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert CREDENTIAL.value not in response.text
    assert revoker.calls == [
        (
            HUMAN,
            RevokeApplicationKeyCommand(PROJECT, APP, CREDENTIAL.key_id, 7),
            IdempotencyContextDTO(HttpMethod.POST, ROUTE, revoker.calls[0][2].key),
        )
    ]
    assert revoker.calls[0][2].key.value == "revoke-original"


def test_human_bearer_needs_no_cookie_csrf_and_keeps_exact_key_scope() -> None:
    revoker, human, application = (
        MockRevoker(),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(revoker, human, application) as client:
        response = client.post(
            ROUTE,
            json=BODY,
            headers={
                "Authorization": "Bearer controlled-human",
                "Idempotency-Key": "revoke-original",
            },
        )
    assert response.status_code == 200
    assert revoker.calls[0][1] == RevokeApplicationKeyCommand(PROJECT, APP, CREDENTIAL.key_id, 7)
    assert isinstance(
        revoker.calls[0][0].authentication_evidence, type(MockAuthenticationEvidence.human_oauth())
    )
    assert len(human.calls) == 1 and application.calls == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expectedAccessRevision": None},
        {"expectedAccessRevision": True},
        {"expectedAccessRevision": 1.5},
        {"expectedAccessRevision": "7"},
        {"expectedAccessRevision": -1},
        {"expectedAccessRevision": 9007199254740992},
        {**BODY, "key": "must-not-be-echoed"},
        {**BODY, "allowedAdapters": ["http"]},
        {**BODY, "changed": True},
    ],
)
def test_body_is_exact_and_invalid_values_never_reach_revocation(body: dict[str, object]) -> None:
    revoker = MockRevoker()
    with client_for(revoker) as client:
        response = client.post(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422 and revoker.calls == []
    assert "must-not-be-echoed" not in response.text and CREDENTIAL.value not in response.text


@pytest.mark.parametrize("revision", [0, 9007199254740991])
def test_safe_integer_revision_boundaries_are_preserved_exactly(revision: int) -> None:
    revoker = MockRevoker()
    with client_for(revoker) as client:
        response = client.post(ROUTE, json={"expectedAccessRevision": revision}, headers=HEADERS)
    assert response.status_code == 200
    assert revoker.calls[0][1].expected_access_revision == revision


@pytest.mark.parametrize("missing", ["Cookie", "Origin", "X-Inframeld-CSRF", "Idempotency-Key"])
def test_cookie_write_requires_identity_csrf_origin_and_original_key(missing: str) -> None:
    revoker = MockRevoker()
    with client_for(revoker) as client:
        response = client.post(
            ROUTE,
            json=BODY,
            headers={key: value for key, value in HEADERS.items() if key != missing},
        )
    assert response.status_code == (
        401 if missing == "Cookie" else 422 if missing == "Idempotency-Key" else 403
    )
    assert revoker.calls == []


def test_foreign_origin_and_competing_credentials_stop_before_revocation() -> None:
    revoker, human, application = (
        MockRevoker(),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(revoker, human, application) as client:
        foreign = client.post(
            ROUTE, json=BODY, headers={**HEADERS, "Origin": "https://foreign.test"}
        )
        assert foreign.status_code == 403 and revoker.calls == []
        assert len(human.calls) == 1 and isinstance(human.calls[0], BrowserSessionCredential)
        authenticated = human.calls.copy()
        competing = client.post(
            ROUTE, json=BODY, headers={**HEADERS, "Authorization": "Bearer controlled-human"}
        )
    assert competing.status_code == 400
    assert human.calls == authenticated and application.calls == 0 and revoker.calls == []


def test_valid_application_gets_human_only_denial_without_human_fallback() -> None:
    revoker, human, application = (
        MockRevoker(failure=AccessDeniedError()),
        MockHumanAuthenticator(),
        MockApplicationAuthenticator(APPLICATION),
    )
    with client_for(revoker, human, application) as client:
        response = client.post(
            ROUTE,
            json=BODY,
            headers={
                "Authorization": "Bearer " + CREDENTIAL.value,
                "Idempotency-Key": "revoke-original",
            },
        )
    assert response.status_code == 403
    assert human.calls == [] and application.calls == 1 and revoker.calls[0][0] == APPLICATION


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (StaleRevisionError(), 409, "stale_revision"),
        (ConflictError(), 409, "conflict"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_handled_service_failures_keep_exact_safe_problems_and_correlation(
    failure: Exception, status: int, code: str
) -> None:
    revoker = MockRevoker(failure=failure)
    with client_for(revoker) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == status and len(revoker.calls) == 1
    assert response.json()["status"] == status and response.json()["code"] == code
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert CREDENTIAL.value not in response.text and "key" not in response.json()


@pytest.mark.parametrize(
    "kind,status",
    [
        ("query", 422),
        ("duplicates", 422),
        ("nonfinite", 422),
        ("array", 422),
        ("wrong-content", 415),
        ("too-large", 413),
    ],
)
def test_existing_bounded_parser_rejects_ambiguous_or_unbounded_input(
    kind: str, status: int
) -> None:
    revoker = MockRevoker()
    body = '{"expectedAccessRevision":7}'
    headers = {**HEADERS, "Content-Type": "application/json"}
    path = ROUTE + ("?expectedAccessRevision=7" if kind == "query" else "")
    if kind == "duplicates":
        body = '{"expectedAccessRevision":7,"expectedAccessRevision":7}'
    if kind == "nonfinite":
        body = '{"expectedAccessRevision":NaN}'
    if kind == "array":
        body = "[]"
    if kind == "wrong-content":
        headers["Content-Type"] = "text/plain"
    if kind == "too-large":
        body = '{"padding":"' + "x" * 32768 + '"}'
    with client_for(revoker) as client:
        response = client.post(path, content=body, headers=headers)
    assert response.status_code == status and revoker.calls == []


def test_native_revoke_operation_declares_exact_safe_request_response_and_security() -> None:
    schema = TestClient(create_app()).get("/v1/openapi.json").json()
    path = "/v1/projects/{project_id}/application-accounts/{application_principal_id}/keys/{key_id}/revoke"
    assert path in schema["paths"], "Native application-key revocation is not registered."
    operation = schema["paths"][path]["post"]
    assert operation["operationId"] == "revokeApplicationKey"
    assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    models = schema["components"]["schemas"]
    request, response = (
        models["ApplicationKeyRevocationRequest"],
        models["ApplicationKeyRevocationResponse"],
    )
    assert request["additionalProperties"] is False and response["additionalProperties"] is False
    assert set(request["required"]) == {"expectedAccessRevision"}
    assert set(request["properties"]) == {"expectedAccessRevision"}
    assert request["properties"]["expectedAccessRevision"]["maximum"] == 9007199254740991
    assert set(response["properties"]) == {
        "operationId",
        "accessRevision",
        "idempotencyExpiresAt",
        "metadata",
    }
    assert set(operation["responses"]) >= {"200", "400", "401", "403", "404", "409", "422", "503"}
