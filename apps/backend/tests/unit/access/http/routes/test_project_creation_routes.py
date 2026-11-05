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

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_creator import ProjectCreator
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.project_creation_routes import (
    create_project_creation_router,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
BODY = {
    "organizationId": str(UUID(int=2)),
    "expectedAccessRevision": 7,
    "name": "production",
    "displayName": "Production",
}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "create-original",
}


class MockCreationAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self) -> None:
        self.calls = 0

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        self.calls += 1
        return ACCESS


class MockProjectCreator(ProjectCreator):
    def __init__(self) -> None:
        self.commands: list[CreateProjectCommand] = []
        self.contexts: list[IdempotencyContextDTO] = []

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProjectCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectCreationResultDTO:
        self.commands.append(command)
        self.contexts.append(context)
        operation = CompletedSynchronousOperationDTO(
            OperationId("created-original"),
            True,
            OperationReplayKind.SAFE_RESULT,
            datetime(2030, 1, 1, tzinfo=UTC),
        )
        return ProjectCreationResultDTO(
            CreatedProjectDTO(
                operation_id=operation.operation_id,
                organization_id=command.organization_id,
                project_id=ProjectId(UUID(int=3)),
                creator_principal_id=access.actor_principal_id,
                name=command.name,
                display_name=command.display_name.value,
                access_revision=1,
                metadata_revision=0,
                initial_actions=tuple(
                    ActionId(value) for value in ProjectCreationPolicy.INITIAL_ACTIONS
                ),
            ),
            operation,
        )


def client_for(service: MockProjectCreator, authenticator: MockCreationAuthenticator) -> TestClient:
    @asynccontextmanager
    async def open_creator() -> AsyncGenerator[MockProjectCreator]:
        yield service

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    app.include_router(
        create_project_creation_router(
            HumanSessionDependency(
                authenticator,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=authenticator,
            ),
            open_creator,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


def test_creation_returns_typed_original_project_and_all_creator_assignments() -> None:
    service, authenticator = MockProjectCreator(), MockCreationAuthenticator()
    with client_for(service, authenticator) as client:
        response = client.post("/v1/projects", json=BODY, headers=HEADERS)
    assert response.status_code == 201
    result = response.json()
    assert result["organizationId"] == str(UUID(int=2)) and result["projectId"] == str(UUID(int=3))
    assert result["name"] == "production" and result["displayName"] == "Production"
    assert result["accessRevision"] == 1 and result["metadataRevision"] == 0
    assert (
        result["operationId"] == "created-original"
        and result["idempotencyExpiresAt"] == "2030-01-01T00:00:00Z"
    )
    assert len(result["initialGrants"]) == 18
    assert all(
        grant["target"] == {"kind": "project", "projectId": str(UUID(int=3))}
        and grant["canGrant"] is True
        for grant in result["initialGrants"]
    )
    assert response.headers["cache-control"] == "no-store"
    assert service.commands[0].organization_id == OrganizationId(UUID(int=2))
    assert (
        service.contexts[0].requested_route == "/v1/projects"
        and service.contexts[0].key.value == "create-original"
    )


@pytest.mark.parametrize(
    "replacement",
    [
        {"expectedAccessRevision": True},
        {"expectedAccessRevision": "7"},
        {"expectedAccessRevision": 7.0},
        {"expectedAccessRevision": -1},
        {"expectedAccessRevision": 2**63},
        {"name": "Production"},
        {"name": "p" * 64},
        {"name": "1project"},
        {"name": "trailing-"},
        {"name": None},
        {"displayName": " "},
        {"displayName": " Trailing "},
        {"displayName": "bad\nlabel"},
        {"displayName": "x" * 129},
        {"actorId": str(UUID(int=9))},
        {"initialGrants": []},
    ],
    ids=[
        "boolean-revision",
        "string-revision",
        "float-revision",
        "negative-revision",
        "overflow-revision",
        "uppercase-name",
        "long-name",
        "digit-name",
        "trailing-hyphen",
        "null-name",
        "blank-label",
        "whitespace-label",
        "control-label",
        "long-label",
        "actor-knob",
        "grant-knob",
    ],
)
def test_invalid_new_input_is_rejected_before_creator(replacement: dict[str, object]) -> None:
    service, authenticator = MockProjectCreator(), MockCreationAuthenticator()
    with client_for(service, authenticator) as client:
        response = client.post("/v1/projects", json=BODY | replacement, headers=HEADERS)
    assert response.status_code == 422
    assert service.commands == []


def test_body_bytes_duplicate_fields_and_media_type_are_bounded_before_effects() -> None:
    service, authenticator = MockProjectCreator(), MockCreationAuthenticator()
    with client_for(service, authenticator) as client:
        headers = HEADERS | {"Content-Type": "application/json"}
        oversized = client.post("/v1/projects", content=b" " * 32769, headers=headers)
        assert oversized.status_code == 413
        assert authenticator.calls == 0
        duplicate = client.post(
            "/v1/projects",
            content=b'{"organizationId":"00000000-0000-0000-0000-000000000002","expectedAccessRevision":7,"name":"first","name":"second","displayName":"Production"}',
            headers=headers,
        )
        assert duplicate.status_code == 422 and duplicate.json()["code"] == "invalid_input"
        invalid_utf8 = client.post("/v1/projects", content=b"\xff", headers=headers)
        assert invalid_utf8.status_code == 422
        media = client.post(
            "/v1/projects", content="{}", headers=HEADERS | {"Content-Type": "text/plain"}
        )
        assert media.status_code == 415
        assert all(
            response.headers["cache-control"] == "no-store"
            for response in (oversized, duplicate, invalid_utf8, media)
        )
    assert service.commands == []


def test_cookie_csrf_bearer_and_unsupported_key_keep_existing_transport_boundaries() -> None:
    service, authenticator = MockProjectCreator(), MockCreationAuthenticator()
    with client_for(service, authenticator) as client:
        denied = client.post(
            "/v1/projects",
            json=BODY,
            headers={"Cookie": HEADERS["Cookie"], "Idempotency-Key": "original"},
        )
        assert denied.status_code == 403 and service.commands == []
        authenticated = authenticator.calls
        app_key = client.post(
            "/v1/projects",
            json=BODY,
            headers={"Authorization": "Bearer ifm_app_controlled", "Idempotency-Key": "original"},
        )
        assert app_key.status_code == 401 and authenticator.calls == authenticated
        bearer = client.post(
            "/v1/projects",
            json=BODY,
            headers={"Authorization": "Bearer controlled-token", "Idempotency-Key": "original"},
        )
        assert bearer.status_code == 201
    assert len(service.commands) == 1 and authenticator.calls == authenticated + 1


def test_ambiguous_credentials_and_duplicate_retry_key_cannot_invoke_creation() -> None:
    service, authenticator = MockProjectCreator(), MockCreationAuthenticator()
    with client_for(service, authenticator) as client:
        competing = client.post(
            "/v1/projects",
            json=BODY,
            headers=HEADERS | {"Authorization": "Bearer controlled-token"},
        )
        assert competing.status_code == 400 and authenticator.calls == 0
        duplicate = client.post(
            "/v1/projects", json=BODY, headers=[*HEADERS.items(), ("Idempotency-Key", "different")]
        )
        assert duplicate.status_code == 422 and duplicate.json()["code"] == "invalid_input"
    assert service.commands == []
