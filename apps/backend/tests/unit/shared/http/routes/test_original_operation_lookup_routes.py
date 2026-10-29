"""Exercise lookup framing and non-disclosure through the real HTTP router."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)

BODY = {
    "installationId": str(UUID(int=1)),
    "organizationId": str(UUID(int=2)),
    "projectId": str(UUID(int=3)),
    "method": "POST",
    "requestedRoute": "/v1/projects/{project_id}/grants",
    "key": "original-key",
    "expectedAuthority": {"family": "project_grant_read", "actionId": "create-access-groups"},
}
HEADERS = {
    "Cookie": "ory_kratos_session=private-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
}
OPERATION = OperationId("original-operation")


class MockLookupAuthenticator(HumanSessionAuthenticator):
    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "private-cookie":
            raise AuthenticationRequiredError()
        return AccessContextDTO(PrincipalId(UUID(int=4)), MockAuthenticationEvidence.browser())


class MockOriginalLookup(OriginalOperationLookup):
    def __init__(self) -> None:
        self.result: (
            CompletedSynchronousOperationDTO
            | AcceptedAsyncOperationDTO
            | InProgressOperationDTO
            | RecoveryRequiredOperationDTO
            | UnresolvedOperationDTO
        ) = UnresolvedOperationDTO()
        self.failure: Exception | None = None
        self.queries: list[LookupOriginalOperationQuery] = []

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> (
        CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | UnresolvedOperationDTO
    ):
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure
        return self.result


def client_for(service: MockOriginalLookup) -> TestClient:
    @asynccontextmanager
    async def open_lookup() -> AsyncGenerator[OriginalOperationLookup]:
        yield service

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_original_operation_lookup_router(
            HumanSessionDependency(
                MockLookupAuthenticator(),
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
            ),
            open_lookup,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize(
    "result,outcome",
    [
        (UnresolvedOperationDTO(), "unresolved"),
        (
            CompletedSynchronousOperationDTO(
                OPERATION,
                False,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
            "completed_synchronous",
        ),
        (AcceptedAsyncOperationDTO(OPERATION, False, None), "accepted_asynchronous"),
        (InProgressOperationDTO(OPERATION), "in_progress"),
        (RecoveryRequiredOperationDTO(OPERATION), "recovery_required"),
    ],
)
def test_permitted_alternatives_preserve_original_identity(
    result: CompletedSynchronousOperationDTO
    | AcceptedAsyncOperationDTO
    | InProgressOperationDTO
    | RecoveryRequiredOperationDTO
    | UnresolvedOperationDTO,
    outcome: str,
) -> None:
    service = MockOriginalLookup()
    service.result = result
    with client_for(service) as client:
        response = client.post("/v1/operations/lookup", json=BODY, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["outcome"] == outcome
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers
    assert len(service.queries) == 1
    assert service.queries[0].key.value == BODY["key"]
    if outcome == "accepted_asynchronous":
        assert response.json()["jobReference"] == "unknown"
        assert "jobId" not in response.json()
        assert response.json()["dispatch"] == "not_established"
    elif outcome == "unresolved":
        assert response.json() == {"outcome": "unresolved"}
    else:
        assert response.json()["operationId"] == OPERATION.value


@pytest.mark.parametrize(
    "headers,status", [({}, 401), ({"Cookie": "ory_kratos_session=private-cookie"}, 403)]
)
def test_authentication_and_csrf_precede_application_lookup(
    headers: dict[str, str], status: int
) -> None:
    service = MockOriginalLookup()
    with client_for(service) as client:
        response = client.post("/v1/operations/lookup", json=BODY, headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert service.queries == []


@pytest.mark.parametrize(
    "failure,status", [(AccessDeniedError(), 403), (DependencyUnavailableError(), 503)]
)
def test_application_failure_does_not_become_unresolved(failure: Exception, status: int) -> None:
    service = MockOriginalLookup()
    service.failure = failure
    with client_for(service) as client:
        response = client.post("/v1/operations/lookup", json=BODY, headers=HEADERS)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "operationId" not in response.json()


@pytest.mark.parametrize(
    "raw,status",
    [
        (b'{"key":"one","key":"two"}', 422),
        (
            b'{"expectedAuthority":{"family":"project_grant_read","family":"project_action_use"}}',
            422,
        ),
        (b"{" + b" " * 32768 + b"}", 413),
        (b'{"key":NaN}', 422),
        (b"\xff", 422),
    ],
)
def test_bounded_strict_json_fails_before_application(raw: bytes, status: int) -> None:
    service = MockOriginalLookup()
    with client_for(service) as client:
        response = client.post(
            "/v1/operations/lookup",
            content=raw,
            headers=HEADERS | {"Content-Type": "application/json"},
        )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert service.queries == []


def test_duplicate_valid_key_is_rejected_instead_of_overwritten() -> None:
    import json

    service = MockOriginalLookup()
    raw = json.dumps(BODY).replace(
        '"key": "original-key"', '"key":"original-key","key":"replacement"'
    )
    with client_for(service) as client:
        response = client.post(
            "/v1/operations/lookup",
            content=raw,
            headers=HEADERS | {"Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert service.queries == []


@pytest.mark.parametrize("field", ["key", "actionId", "requestedRoute"])
def test_whitespace_only_identity_fields_are_controlled_validation_failures(field: str) -> None:
    from copy import deepcopy

    service = MockOriginalLookup()
    body = deepcopy(BODY)
    if field == "actionId":
        guard = body["expectedAuthority"]
        assert isinstance(guard, dict)
        guard["actionId"] = "   "
    else:
        body[field] = "   "
    with (
        client_for(service) as existing,
        TestClient(existing.app, raise_server_exceptions=False) as client,
    ):
        response = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
    assert response.status_code == 422
    assert service.queries == []


def test_original_guard_is_required_before_application_lookup() -> None:
    service = MockOriginalLookup()
    body = {key: value for key, value in BODY.items() if key != "expectedAuthority"}
    with client_for(service) as client:
        response = client.post("/v1/operations/lookup", json=body, headers=HEADERS)
    assert response.status_code == 422
    assert service.queries == []
