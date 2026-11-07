from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipient_dto import GrantRecipientDTO
from inframeld_backend.access.application.dtos.grant_recipients_page_dto import (
    GrantRecipientsPageDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_grant_recipients_reader import (
    ProjectGrantRecipientsReader,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.project_grant_recipients_routes import (
    create_project_grant_recipients_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
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
TARGET = UUID(int=6)
ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
PATH = f"/v1/projects/{PROJECT.value}/grant-recipients"
COOKIE = {"Cookie": "ory_kratos_session=controlled"}
BEARER = {"Authorization": "Bearer controlled"}
QUERY = f"targetKind=project&targetId={PROJECT.value}&actionId=inspect-budget"


class MockAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return ACCESS


class MockRecipientsReader(ProjectGrantRecipientsReader):
    def __init__(self) -> None:
        self.calls: list[tuple[AccessContextDTO, ListProjectGrantRecipientsQuery]] = []
        self.closed = 0
        self.error: Exception | None = None

    @override
    async def list_recipients(
        self, *, access: AccessContextDTO, query: ListProjectGrantRecipientsQuery
    ) -> GrantRecipientsPageDTO:
        self.calls.append((access, query))
        if self.error is not None:
            raise self.error
        return GrantRecipientsPageDTO(
            items=(
                GrantRecipientDTO(
                    principal_id=PrincipalId(UUID(int=10)),
                    display_name="Bob",
                    kind=PrincipalKind.HUMAN,
                ),
            ),
            next_cursor="opaque_cursor",
        )


def _client(reader: MockRecipientsReader) -> TestClient:
    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ProjectGrantRecipientsReader]:
        try:
            yield reader
        finally:
            reader.closed += 1

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    auth = MockAuthentication()
    app.include_router(
        create_project_grant_recipients_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(
                    AccessContextDTO(
                        PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
                    ),
                    failure=AuthenticationRequiredError(),
                ),
            ),
            open_reader,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("kind", ["project", "access-group", "application-account"])
@pytest.mark.parametrize("headers", [COOKIE, BEARER])
def test_scalar_target_maps_to_closed_typed_scope_and_safe_page(
    kind: str, headers: dict[str, str]
) -> None:
    reader = MockRecipientsReader()
    target_id = PROJECT.value if kind == "project" else TARGET
    action = {
        "project": "inspect-budget",
        "access-group": "add-documents",
        "application-account": "issue-application-keys",
    }[kind]
    with _client(reader) as client:
        response = client.get(
            PATH,
            params={
                "targetKind": kind,
                "targetId": str(target_id),
                "actionId": action,
                "limit": 2,
                "cursor": "opaque_cursor",
            },
            headers=headers,
        )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [{"principalId": str(UUID(int=10)), "displayName": "Bob", "kind": "human"}],
        "nextCursor": "opaque_cursor",
    }
    assert len(reader.calls) == 1 and reader.closed == 1
    access, query = reader.calls[0]
    assert (
        access == ACCESS
        and query.project_id == PROJECT
        and query.limit == 2
        and query.cursor == "opaque_cursor"
    )
    expected = (
        ProjectGrantTargetDTO(project_id=PROJECT)
        if kind == "project"
        else AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=AccessGroupId(TARGET))
        if kind == "access-group"
        else ApplicationAccountGrantTargetDTO(
            project_id=PROJECT, application_principal_id=PrincipalId(TARGET)
        )
    )
    assert query.target == expected and query.action_id.value == action


@pytest.mark.parametrize(
    "query",
    [
        "",
        "targetKind=project",
        QUERY.replace("project&", "organization&"),
        QUERY.replace("project&", "access_group&"),
        QUERY.replace(str(PROJECT.value), "invalid"),
        QUERY.replace(str(PROJECT.value), str(UUID(int=99))),
        QUERY.replace("inspect-budget", ""),
        QUERY + "&limit=0",
        QUERY + "&limit=101",
        QUERY + "&cursor=",
        QUERY + "&cursor=bad%2Bcursor",
        QUERY + "&targetKind=project",
        QUERY + "&targetId=" + str(TARGET),
        QUERY + "&actionId=other",
        QUERY + "&limit=1&limit=2",
        QUERY + "&cursor=a&cursor=b",
        QUERY + "&target[kind]=project",
        QUERY + "&offset=1",
    ],
)
def test_invalid_scalar_query_never_opens_a_reader(query: str) -> None:
    reader = MockRecipientsReader()
    with _client(reader) as client:
        response = client.get(PATH + "?" + query, headers=COOKIE)
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert reader.calls == [] and reader.closed == 0


def test_get_has_no_body_and_requires_no_mutation_or_csrf_headers() -> None:
    reader = MockRecipientsReader()
    with _client(reader) as client:
        response = client.request("GET", PATH + "?" + QUERY, content=b"{}", headers=COOKIE)
    assert response.status_code == 422 and response.json()["code"] == "invalid_input"
    assert reader.calls == [] and reader.closed == 0


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer ifm_app_private"}, COOKIE | BEARER]
)
def test_unsupported_or_competing_credentials_do_not_disclose_choices(
    headers: dict[str, str],
) -> None:
    reader = MockRecipientsReader()
    with _client(reader) as client:
        response = client.get(PATH + "?" + QUERY, headers=headers)
    assert response.status_code in (400, 401) and response.headers["cache-control"] == "no-store"
    assert reader.calls == [] and reader.closed == 0


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_current_denials_close_the_request_and_are_declared(
    error: Exception, status: int, code: str
) -> None:
    reader = MockRecipientsReader()
    reader.error = error
    with _client(reader) as client:
        response = client.get(PATH + "?" + QUERY, headers=COOKIE)
        schema = client.get("/openapi.json").json()
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store" and reader.closed == 1
    assert (
        "application/problem+json"
        in schema["paths"]["/v1/projects/{project_id}/grant-recipients"]["get"]["responses"][
            str(status)
        ]["content"]
    )
