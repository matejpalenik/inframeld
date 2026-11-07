from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.project_membership_change_scenarios import (
    ACCESS,
    ADD,
    BOB,
    PROJECT,
    REMOVE,
    ROUTE,
    MembershipChangeScenario,
)

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_membership_change_service_factory import (
    ProjectMembershipChangeServiceFactory,
)
from inframeld_backend.access.application.protocols.project_membership_changer import (
    ProjectMembershipChanger,
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
from inframeld_backend.access.http.routes.project_membership_routes import (
    create_project_membership_router,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "member-bob",
}


class MockMembershipAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        return ACCESS


class MockMembershipChanger(ProjectMembershipChanger):
    def __init__(self, changed: bool = True) -> None:
        self.result = replace(
            MembershipChangeScenario().results.result,
            change_kind=ProjectMembershipChangeKind.ADD,
            changed=changed,
            access_revision=7 + int(changed),
            status_code=201 if changed else 200,
        )
        self.calls: list[
            tuple[AddProjectMemberCommand | RemoveProjectMemberCommand, IdempotencyContextDTO]
        ] = []
        self.error: ApplicationError | None = None

    @override
    async def add_member(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def remove_member(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return replace(self.result, change_kind=ProjectMembershipChangeKind.REMOVE, status_code=200)


class MockMembershipChangeServiceFactory(ProjectMembershipChangeServiceFactory):
    def __init__(self, service: MockMembershipChanger) -> None:
        self._service = service

    @override
    @asynccontextmanager
    async def open(self) -> AsyncGenerator[ProjectMembershipChanger]:
        yield self._service


def client_for(service: MockMembershipChanger) -> TestClient:
    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    authenticator = MockMembershipAuthenticator()
    app.include_router(
        create_project_membership_router(
            ProductAccessDependency(
                authenticator,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=authenticator,
                application_authenticator=MockApplicationAuthenticator(
                    AccessContextDTO(
                        PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
                    ),
                    failure=AuthenticationRequiredError(),
                ),
            ),
            MockMembershipChangeServiceFactory(service),
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("changed", [True, False])
def test_put_returns_original_status_and_complete_membership_receipt(changed: bool) -> None:
    service = MockMembershipChanger(changed)
    with client_for(service) as client:
        response = client.put(ROUTE, json={"expectedAccessRevision": 7}, headers=HEADERS)
    assert response.status_code == (201 if changed else 200)
    assert response.json() == {
        "operationId": "metadata-original",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
        "projectId": str(PROJECT.value),
        "principalId": str(BOB.id.value),
        "accessRevision": 7 + int(changed),
        "member": True,
        "changed": changed,
    }
    assert response.headers["cache-control"] == "no-store"
    command, context = service.calls[0]
    assert command == ADD and context.method == "PUT" and context.requested_route == ROUTE
    assert context.key.value == "member-bob"


@pytest.mark.parametrize("changed", [True, False])
def test_delete_carries_reviewed_revision_only_in_required_query(changed: bool) -> None:
    service = MockMembershipChanger(changed)
    with client_for(service) as client:
        response = client.delete(ROUTE, params={"expectedAccessRevision": 7}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["removed"] is True and body["changed"] is changed
    assert body["accessRevision"] == 7 + int(changed) and body["projectId"] == str(PROJECT.value)
    assert body["principalId"] == str(BOB.id.value) and body["operationId"] == "metadata-original"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls[0][0] == REMOVE and service.calls[0][1].method == "DELETE"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "expectedAccessRevision=-1",
        "expectedAccessRevision=1.5",
        "expectedAccessRevision=1.0",
        "expectedAccessRevision=true",
        "expectedAccessRevision=00",
        "expectedAccessRevision=07",
        "expectedAccessRevision=0007",
        "expectedAccessRevision=" + "0" * 20,
        "expectedAccessRevision=" + "0" * 19 + "7",
        "expectedAccessRevision=9223372036854775808",
        "expectedAccessRevision=7&expectedAccessRevision=7",
        "expectedAccessRevision=7&extra=1",
    ],
)
def test_delete_rejects_missing_invalid_duplicate_or_unknown_query_without_call(query: str) -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.delete(ROUTE + "?" + query, headers=HEADERS)
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert not service.calls


@pytest.mark.parametrize("revision", [0, 2**53 - 1])
def test_delete_accepts_canonical_integer_revision_boundaries(revision: int) -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.delete(
            ROUTE, params={"expectedAccessRevision": revision}, headers=HEADERS
        )
    assert response.status_code == 200
    assert service.calls[0][0].expected_access_revision == revision


def test_delete_rejects_a_body_instead_of_reading_revision_from_it() -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.request(
            "DELETE",
            ROUTE + "?expectedAccessRevision=7",
            json={"expectedAccessRevision": 7},
            headers=HEADERS,
        )
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expectedAccessRevision": True},
        {"expectedAccessRevision": "7"},
        {"expectedAccessRevision": -1},
        {"expectedAccessRevision": 7, "canGrant": True},
        {"expectedAccessRevision": 2**53},
    ],
)
def test_put_rejects_invalid_or_extra_fields(body: dict[str, object]) -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.put(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize(
    "content,status",
    [
        ("{" + '"expectedAccessRevision":7,' + '"expectedAccessRevision":7}', 422),
        ('{"expectedAccessRevision":' + ("1" * 32769) + "}", 413),
        ("[7]", 422),
        ("{", 422),
    ],
    ids=["duplicate", "oversized", "array", "malformed"],
)
def test_put_bounds_json_and_rejects_duplicate_fields(content: str, status: int) -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.put(
            ROUTE, content=content, headers={**HEADERS, "Content-Type": "application/json"}
        )
    assert response.status_code == status and not service.calls


def test_put_requires_json_media_type() -> None:
    service = MockMembershipChanger()
    with client_for(service) as client:
        response = client.put(ROUTE, content='{"expectedAccessRevision":7}', headers=HEADERS)
    assert response.status_code == 415 and not service.calls


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_cookie_mutations_require_origin_and_csrf_but_bearer_uses_its_own_family(
    method: str,
) -> None:
    service = MockMembershipChanger()
    route = ROUTE if method == "PUT" else ROUTE + "?expectedAccessRevision=7"
    payload = {"expectedAccessRevision": 7} if method == "PUT" else None
    with client_for(service) as client:
        denied = client.request(
            method,
            route,
            headers={"Cookie": HEADERS["Cookie"], "Idempotency-Key": "missing-csrf"},
            json=payload,
        )
        assert denied.status_code == 403 and not service.calls
        allowed = client.request(
            method,
            route,
            headers={
                "Authorization": "Bearer controlled-human-token",
                "Idempotency-Key": "bearer-write",
            },
            json=payload,
        )
    assert allowed.status_code == (201 if method == "PUT" else 200) and len(service.calls) == 1


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": " "}, {"Idempotency-Key": "x" * 129}])
def test_missing_or_invalid_idempotency_key_never_calls_operation(headers: dict[str, str]) -> None:
    service = MockMembershipChanger()
    credentials = {key: value for key, value in HEADERS.items() if key != "Idempotency-Key"}
    with client_for(service) as client:
        response = client.put(
            ROUTE, json={"expectedAccessRevision": 7}, headers={**credentials, **headers}
        )
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize("error", [StaleRevisionError(), ConflictError("Protected detail")])
def test_state_conflict_uses_existing_safe_problem_without_private_detail(
    error: ApplicationError,
) -> None:
    service = MockMembershipChanger()
    service.error = error
    with client_for(service) as client:
        response = client.delete(ROUTE + "?expectedAccessRevision=7", headers=HEADERS)
    assert response.status_code == 409 and response.headers["cache-control"] == "no-store"
    assert "Protected detail" not in response.text


def test_native_schema_has_distinct_operations_and_required_delete_query() -> None:
    with client_for(MockMembershipChanger()) as client:
        paths = client.get("/openapi.json").json()["paths"]
    operations = paths["/v1/projects/{project_id}/members/{principal_id}"]
    assert operations["put"]["operationId"] == "addProjectMember"
    delete = operations["delete"]
    assert delete["operationId"] == "removeProjectMember" and "requestBody" not in delete
    revision = next(
        item for item in delete["parameters"] if item["name"] == "expectedAccessRevision"
    )
    assert (
        revision["in"] == "query"
        and revision["required"]
        and revision["schema"]["type"] == "integer"
    )
