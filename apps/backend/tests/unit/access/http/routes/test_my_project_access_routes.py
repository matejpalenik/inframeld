from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_page_dto import (
    MyProjectAccessPageDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.my_project_access_reader import (
    MyProjectAccessReader,
)
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.my_project_access_routes import (
    create_my_project_access_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

PROJECT = ProjectId(UUID(int=3))
PRINCIPAL = PrincipalId(UUID(int=4))
GROUP = AccessGroupId(UUID(int=5))
APP = PrincipalId(UUID(int=6))
COOKIE = {"Cookie": "ory_kratos_session=private-test-cookie"}
BEARER = {"Authorization": "Bearer private-test-token"}
PATH = f"/v1/projects/{PROJECT.value}/my-access"


class MockAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        evidence = (
            MockAuthenticationEvidence.human_oauth()
            if isinstance(credential, HumanAccessTokenCredential)
            else MockAuthenticationEvidence.browser()
        )
        return AccessContextDTO(PRINCIPAL, evidence)


class MockOwnAccessReader(MyProjectAccessReader):
    def __init__(self) -> None:
        self.calls: list[GetMyProjectAccessQuery] = []
        self.closed = 0
        self.error: Exception | None = None

    @override
    async def get_access(
        self, *, access: AccessContextDTO, query: GetMyProjectAccessQuery
    ) -> MyProjectAccessPageDTO:
        assert access.actor_principal_id == PRINCIPAL
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return MyProjectAccessPageDTO(
            project_id=PROJECT,
            principal_id=PRINCIPAL,
            access_revision=7,
            grants=(
                MyProjectAccessGrantDTO(
                    ProjectGrantTargetDTO(PROJECT), ActionId("inspect-budget"), False
                ),
                MyProjectAccessGrantDTO(
                    AccessGroupGrantTargetDTO(PROJECT, GROUP), ActionId("add-documents"), False
                ),
                MyProjectAccessGrantDTO(
                    ApplicationAccountGrantTargetDTO(PROJECT, APP),
                    ActionId("revoke-application-keys"),
                    True,
                ),
            ),
            group_memberships=(GROUP,),
            group_managements=(GROUP,),
            next_cursor="next_page",
        )


def _client(reader: MockOwnAccessReader) -> TestClient:
    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[MyProjectAccessReader]:
        try:
            yield reader
        finally:
            reader.closed += 1

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    auth = MockAuthentication()
    app.include_router(
        create_my_project_access_router(
            HumanSessionDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
            ),
            open_reader,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("headers", [COOKIE, BEARER])
def test_own_page_exposes_current_revision_and_exact_typed_relationships(
    headers: dict[str, str],
) -> None:
    reader = MockOwnAccessReader()
    with _client(reader) as client:
        response = client.get(PATH + "?limit=5&cursor=opaque_cursor", headers=headers)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "projectId": str(PROJECT.value),
        "principalId": str(PRINCIPAL.value),
        "accessRevision": 7,
        "grants": [
            {
                "target": {"kind": "project", "projectId": str(PROJECT.value)},
                "actionId": "inspect-budget",
                "canGrant": False,
            },
            {
                "target": {
                    "kind": "access-group",
                    "projectId": str(PROJECT.value),
                    "accessGroupId": str(GROUP.value),
                },
                "actionId": "add-documents",
                "canGrant": False,
            },
            {
                "target": {
                    "kind": "application-account",
                    "projectId": str(PROJECT.value),
                    "applicationPrincipalId": str(APP.value),
                },
                "actionId": "revoke-application-keys",
                "canGrant": True,
            },
        ],
        "groupMemberships": [{"accessGroupId": str(GROUP.value)}],
        "groupManagements": [{"accessGroupId": str(GROUP.value)}],
        "nextCursor": "next_page",
    }
    assert reader.calls == [GetMyProjectAccessQuery(PROJECT, 5, "opaque_cursor")]
    assert reader.closed == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "cursor=", "cursor=bad%2Bcursor"])
def test_invalid_page_fields_never_open_the_own_reader(query: str) -> None:
    reader = MockOwnAccessReader()
    with _client(reader) as client:
        response = client.get(PATH + "?" + query, headers=COOKIE)
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert reader.calls == [] and reader.closed == 0


@pytest.mark.parametrize("query", ["limit=1&limit=2", "cursor=a&cursor=b", "principalId=other"])
def test_ambiguous_or_principal_selected_read_is_rejected(query: str) -> None:
    reader = MockOwnAccessReader()
    with _client(reader) as client:
        response = client.get(PATH + "?" + query, headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert reader.calls == [] and reader.closed == 0


def test_bodyless_read_rejects_a_body_without_reading_relationships() -> None:
    reader = MockOwnAccessReader()
    with _client(reader) as client:
        response = client.request("GET", PATH, content=b"{}", headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store" and reader.calls == []


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer ifm_app_private"}, COOKIE | BEARER]
)
def test_missing_unsupported_or_competing_credentials_cannot_read(headers: dict[str, str]) -> None:
    reader = MockOwnAccessReader()
    with _client(reader) as client:
        response = client.get(PATH, headers=headers)
    assert response.status_code in (400, 401)
    assert response.headers["cache-control"] == "no-store" and reader.calls == []


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_safe_errors_close_the_reader_and_preserve_native_operation_contract(
    error: Exception, status: int, code: str
) -> None:
    reader = MockOwnAccessReader()
    reader.error = error
    with _client(reader) as client:
        response = client.get(PATH, headers=COOKIE)
        operation = client.get("/openapi.json").json()["paths"][
            "/v1/projects/{project_id}/my-access"
        ]["get"]
    assert operation["operationId"] == "getMyProjectAccess"
    assert "application/problem+json" in operation["responses"][str(status)]["content"]
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store" and reader.closed == 1
