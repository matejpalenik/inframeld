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
from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.application.dtos.project_members_page_dto import ProjectMembersPageDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_members_reader import (
    ProjectMembersReader,
)
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_members_routes import (
    create_project_members_router,
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
ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
COOKIE = {"Cookie": "ory_kratos_session=private-test-cookie"}
BEARER = {"Authorization": "Bearer private-test-token"}
URL = f"/v1/projects/{PROJECT.value}/members"


class MockHumanAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return ACCESS


class MockMembersReader(ProjectMembersReader):
    def __init__(self) -> None:
        self.calls: list[tuple[AccessContextDTO, ListProjectMembersQuery]] = []
        self.closed = 0
        self.error: Exception | None = None
        self.result = ProjectMembersPageDTO(
            PROJECT,
            12,
            (
                ProjectMemberDTO(
                    PrincipalId(UUID(int=10)), " legacy\nlabel " + "a" * 1000, PrincipalKind.HUMAN
                ),
                ProjectMemberDTO(PrincipalId(UUID(int=20)), "App", PrincipalKind.APPLICATION),
            ),
            "opaque_cursor",
        )

    @override
    async def list_members(
        self, *, access: AccessContextDTO, query: ListProjectMembersQuery
    ) -> ProjectMembersPageDTO:
        self.calls.append((access, query))
        if self.error is not None:
            raise self.error
        return self.result


def client_for(reader: MockMembersReader) -> TestClient:
    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ProjectMembersReader]:
        try:
            yield reader
        finally:
            reader.closed += 1

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    auth = MockHumanAuthentication()
    app.include_router(
        create_project_members_router(
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
def test_get_uses_current_human_auth_without_write_headers_and_preserves_safe_fields(
    headers: dict[str, str],
) -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get(URL, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "projectId": str(PROJECT.value),
        "accessRevision": 12,
        "items": [
            {
                "principalId": str(item.principal_id.value),
                "displayName": item.display_name,
                "kind": item.kind.value,
            }
            for item in reader.result.items
        ],
        "nextCursor": "opaque_cursor",
    }
    assert reader.calls == [(ACCESS, ListProjectMembersQuery(PROJECT))]
    assert reader.closed == 1


def test_bounded_query_maps_exact_uuid_limit_and_opaque_cursor() -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get(URL + "?limit=2&cursor=opaque_cursor", headers=COOKIE)
    assert response.status_code == 200
    assert reader.calls == [(ACCESS, ListProjectMembersQuery(PROJECT, 2, "opaque_cursor"))]


def test_empty_continuation_keeps_authoritative_revision_and_explicit_null() -> None:
    reader = MockMembersReader()
    reader.result = ProjectMembersPageDTO(PROJECT, 19, (), None)
    with client_for(reader) as client:
        response = client.get(URL + "?cursor=opaque_cursor", headers=COOKIE)
    assert response.status_code == 200
    assert response.json() == {
        "projectId": str(PROJECT.value),
        "accessRevision": 19,
        "items": [],
        "nextCursor": None,
    }


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=true",
        "limit=2.5",
        "cursor=",
        "cursor=bad%2Bvalue",
        "cursor=" + "a" * 1025,
    ],
)
def test_invalid_pagination_fails_before_application_observation(query: str) -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get(URL + "?" + query, headers=COOKIE)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert not reader.calls and reader.closed == 0


@pytest.mark.parametrize(
    "query", ["limit=1&limit=2", "cursor=a&cursor=b", "offset=1", "filter=human"]
)
def test_ambiguous_or_unsupported_query_never_invokes_reader(query: str) -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get(URL + "?" + query, headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store"
    assert not reader.calls


def test_get_body_is_rejected_without_application_io() -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.request("GET", URL, content=b"{}", headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store"
    assert not reader.calls


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer ifm_app_private"}, COOKIE | BEARER]
)
def test_missing_application_or_competing_credentials_cannot_read(headers: dict[str, str]) -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get(URL, headers=headers)
    assert response.status_code in (400, 401)
    assert response.headers["cache-control"] == "no-store"
    assert not reader.calls


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_safe_failures_close_reader_and_match_declared_problem_contract(
    error: Exception, status: int, code: str
) -> None:
    reader = MockMembersReader()
    reader.error = error
    with client_for(reader) as client:
        schema = client.get("/openapi.json").json()
        declared = schema["paths"]["/v1/projects/{project_id}/members"]["get"]["responses"]
        response = client.get(URL, headers=COOKIE)
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert "application/problem+json" in declared[str(status)]["content"]
    assert reader.closed == 1


def test_malformed_project_id_is_validation_error_without_observation() -> None:
    reader = MockMembersReader()
    with client_for(reader) as client:
        response = client.get("/v1/projects/not-a-uuid/members", headers=COOKIE)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert not reader.calls
