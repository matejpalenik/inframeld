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
from inframeld_backend.access.application.dtos.project_action_grant_dto import ProjectActionGrantDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_dto import (
    ProjectActionGrantsPageDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_action_grants_reader import (
    ProjectActionGrantsReader,
)
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_action_grant_routes import (
    create_project_action_grant_router,
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
ACTION = ActionId("create-access-groups")
ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
COOKIE = {"Cookie": "ory_kratos_session=private-test-cookie"}
BEARER = {"Authorization": "Bearer private-test-token"}
PATH = f"/v1/projects/{PROJECT.value}/grants"
URL = PATH + "?actionId=" + ACTION.value


class MockAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return ACCESS


class MockGrantsReader(ProjectActionGrantsReader):
    def __init__(self) -> None:
        self.calls: list[tuple[AccessContextDTO, ListProjectActionGrantsQuery]] = []
        self.closed = 0
        self.error: Exception | None = None
        self.result = ProjectActionGrantsPageDTO(
            PROJECT,
            ACTION,
            (ProjectActionGrantDTO(PrincipalId(UUID(int=10)), ACTION, False),),
            "opaque_cursor",
        )

    @override
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListProjectActionGrantsQuery
    ) -> ProjectActionGrantsPageDTO:
        self.calls.append((access, query))
        if self.error is not None:
            raise self.error
        return self.result


def client_for(reader: MockGrantsReader) -> TestClient:
    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ProjectActionGrantsReader]:
        try:
            yield reader
        finally:
            reader.closed += 1

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    auth = MockAuthentication()
    app.include_router(
        create_project_action_grant_router(
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
def test_get_maps_exact_flat_assignment_without_write_headers(headers: dict[str, str]) -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.get(URL + "&limit=2&cursor=opaque_cursor", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "projectId": str(PROJECT.value),
                "recipientPrincipalId": str(UUID(int=10)),
                "actionId": ACTION.value,
                "canGrant": False,
            }
        ],
        "nextCursor": "opaque_cursor",
    }
    assert reader.calls == [
        (ACCESS, ListProjectActionGrantsQuery(PROJECT, ACTION, 2, "opaque_cursor"))
    ]
    assert reader.closed == 1


@pytest.mark.parametrize(
    "query",
    [
        "",
        "actionId=",
        "actionId=%20",
        "actionId=" + "x" * 101,
        "actionId=inspect-budget&limit=0",
        "actionId=inspect-budget&limit=101",
        "actionId=inspect-budget&cursor=",
        "actionId=inspect-budget&cursor=bad%2Bcursor",
    ],
)
def test_invalid_fields_are_safe_validation_without_observation(query: str) -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.get(PATH + "?" + query, headers=COOKIE)
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert not reader.calls


@pytest.mark.parametrize(
    "suffix", ["&actionId=inspect-budget", "&limit=1&limit=2", "&cursor=a&cursor=b", "&offset=1"]
)
def test_duplicate_or_unknown_query_is_rejected(suffix: str) -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.get(URL + suffix, headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store" and not reader.calls


def test_get_body_is_rejected_without_application_io() -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.request("GET", URL, content=b"{}", headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store" and not reader.calls


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer ifm_app_private"}, COOKIE | BEARER]
)
def test_unsupported_or_competing_credentials_do_not_read(headers: dict[str, str]) -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.get(URL, headers=headers)
    assert response.status_code in (400, 401)
    assert response.headers["cache-control"] == "no-store" and not reader.calls


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_safe_errors_close_session_and_are_declared(
    error: Exception, status: int, code: str
) -> None:
    reader = MockGrantsReader()
    reader.error = error
    with client_for(reader) as client:
        schema = client.get("/openapi.json").json()
        responses = schema["paths"]["/v1/projects/{project_id}/grants"]["get"]["responses"]
        response = client.get(URL, headers=COOKIE)
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert "application/problem+json" in responses[str(status)]["content"]
    assert reader.closed == 1


def test_retired_post_with_original_body_is_method_not_allowed_before_get_validation() -> None:
    reader = MockGrantsReader()
    with client_for(reader) as client:
        response = client.post(
            PATH,
            headers=COOKIE | {"Idempotency-Key": "retired-original-post"},
            json={
                "recipientPrincipalId": str(UUID(int=10)),
                "actionId": "create-access-groups",
                "canGrant": False,
                "expectedAccessRevision": 0,
            },
        )
    assert response.status_code == 405
    assert response.headers["cache-control"] == "no-store"
    assert "GET" in response.headers["allow"]
    assert reader.calls == [] and reader.closed == 0
