from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID, PROJECT_ID, SAVED_RESULT

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_change_result_dto import (
    ProjectMetadataChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_metadata_changer import (
    ProjectMetadataChanger,
)
from inframeld_backend.access.application.protocols.project_metadata_reader import (
    ProjectMetadataReader,
)
from inframeld_backend.access.application.protocols.project_name_resolver import ProjectNameResolver
from inframeld_backend.access.application.queries.get_project_metadata_query import (
    GetProjectMetadataQuery,
)
from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_metadata_routes import (
    create_project_metadata_router,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

HEADERS = {
    "Cookie": "ory_kratos_session=private-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "original",
}


class MockMetadataAuthenticator(HumanSessionAuthenticator):
    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        return ACCESS


class MockMetadataOperations(ProjectMetadataReader, ProjectMetadataChanger, ProjectNameResolver):
    def __init__(self) -> None:
        self.commands: list[UpdateProjectMetadataCommand] = []
        self.resolution_error: Exception | None = None
        self.result = ProjectMetadataDTO(
            ORGANIZATION_ID, PROJECT_ID, None, " legacy\nlabel " + "a" * 1000, 0
        )

    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectMetadataQuery
    ) -> ProjectMetadataDTO:
        return self.result

    @override
    async def resolve(
        self, *, access: AccessContextDTO, query: ResolveProjectNameQuery
    ) -> ProjectMetadataDTO:
        if self.resolution_error is not None:
            raise self.resolution_error
        return self.result

    @override
    async def update(
        self,
        *,
        access: AccessContextDTO,
        command: UpdateProjectMetadataCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMetadataChangeResultDTO:
        self.commands.append(command)
        return ProjectMetadataChangeResultDTO(self.result, SAVED_RESULT)


def client_for(service: MockMetadataOperations) -> TestClient:
    @asynccontextmanager
    async def open_service() -> AsyncGenerator[MockMetadataOperations]:
        yield service

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    app.include_router(
        create_project_metadata_router(
            HumanSessionDependency(
                MockMetadataAuthenticator(),
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
            ),
            open_service,
            open_service,
            open_service,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


def test_current_metadata_and_selector_only_update_preserve_raw_legacy_label() -> None:
    service = MockMetadataOperations()
    with client_for(service) as client:
        response = client.get(f"/v1/projects/{PROJECT_ID.value}/metadata", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["displayName"] == service.result.display_name
        assert response.headers["cache-control"] == "no-store"
        response = client.patch(
            f"/v1/projects/{PROJECT_ID.value}/metadata",
            json={"expectedMetadataRevision": 0, "name": "support"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert service.commands[-1].display_name is None


@pytest.mark.parametrize(
    "body",
    [
        {"expectedMetadataRevision": 0, "name": None},
        {"expectedMetadataRevision": 0, "displayName": " "},
        {"expectedMetadataRevision": True, "name": "support"},
    ],
)
def test_invalid_replacement_never_invokes_change(body: dict[str, object]) -> None:
    service = MockMetadataOperations()
    with client_for(service) as client:
        response = client.patch(
            f"/v1/projects/{PROJECT_ID.value}/metadata", json=body, headers=HEADERS
        )
    assert response.status_code == 422
    assert not service.commands


def test_bounded_duplicate_json_and_cookie_csrf_fail_without_change() -> None:
    service = MockMetadataOperations()
    with client_for(service) as client:
        url = f"/v1/projects/{PROJECT_ID.value}/metadata"
        headers = HEADERS | {"Content-Type": "application/json"}
        assert client.patch(url, content=b" " * 32769, headers=headers).status_code == 413
        duplicate = client.patch(
            url, content=b'{"expectedMetadataRevision":0,"name":"a","name":"b"}', headers=headers
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["code"] == "invalid_input"
        assert (
            client.patch(
                url,
                json={"expectedMetadataRevision": 0, "name": "support"},
                headers={
                    "Cookie": "ory_kratos_session=private-cookie",
                    "Idempotency-Key": "original",
                },
            ).status_code
            == 403
        )
    assert not service.commands


def test_non_bmp_label_uses_codepoint_limit_and_name_lookup_never_normalizes() -> None:
    service = MockMetadataOperations()
    label = "😀" * 126 + "e\u0301"
    with client_for(service) as client:
        url = f"/v1/projects/{PROJECT_ID.value}/metadata"
        assert (
            client.patch(
                url, json={"expectedMetadataRevision": 0, "displayName": label}, headers=HEADERS
            ).status_code
            == 200
        )
        submitted = service.commands[-1].display_name
        assert submitted is not None and submitted.value == label
        assert (
            client.patch(
                url,
                json={"expectedMetadataRevision": 0, "displayName": "😀" * 129},
                headers=HEADERS,
            ).status_code
            == 422
        )
        assert client.get("/v1/projects/by-name/Support", headers=HEADERS).status_code == 422


def test_retired_name_is_safe_404_guidance_without_redirect() -> None:
    from inframeld_backend.access.application.errors.retired_project_name_error import (
        RetiredProjectNameError,
    )
    from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

    service = MockMetadataOperations()
    service.resolution_error = RetiredProjectNameError(PROJECT_ID, ResourceName("research"))
    with client_for(service) as client:
        response = client.get("/v1/projects/by-name/support", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"
    assert str(PROJECT_ID.value) in response.json()["detail"]
    assert "research" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers


def test_patch_framing_problems_match_declared_status_and_media_without_mutation() -> None:
    service = MockMetadataOperations()
    with client_for(service) as client:
        schema = client.get("/openapi.json").json()
        responses = schema["paths"]["/v1/projects/{project_id}/metadata"]["patch"]["responses"]
        for content, content_type, status in [
            (b" " * 32769, "application/json", 413),
            (b"{}", "text/plain", 415),
        ]:
            response = client.patch(
                f"/v1/projects/{PROJECT_ID.value}/metadata",
                content=content,
                headers=HEADERS | {"Content-Type": content_type},
            )
            assert response.status_code == response.json()["status"] == status
            assert response.headers["content-type"] == "application/problem+json"
            assert response.headers["cache-control"] == "no-store"
            assert set(responses[str(status)]["content"]) == {"application/problem+json"}
            assert responses[str(status)]["content"]["application/problem+json"]["schema"][
                "$ref"
            ].endswith("/ProblemDetails")
    assert not service.commands
