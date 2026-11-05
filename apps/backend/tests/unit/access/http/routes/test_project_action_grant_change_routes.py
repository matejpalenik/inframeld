from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_action_grant_change_kind import (
    ProjectActionGrantChangeKind,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
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
from inframeld_backend.access.http.routes.project_action_grant_change_routes import (
    create_project_action_grant_change_router,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

PROJECT, RECIPIENT, ACTOR = (
    ProjectId(UUID(int=3)),
    PrincipalId(UUID(int=2)),
    PrincipalId(UUID(int=1)),
)
ACTION = ActionId("inspect-budget")
ROUTE = f"/v1/projects/{PROJECT.value}/grants/{RECIPIENT.value}/{ACTION.value}"
HEADERS = {
    "Cookie": "ory_kratos_session=controlled",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "grant-bob",
}
OPERATION = CompletedSynchronousOperationDTO(
    OperationId("original-grant"),
    False,
    OperationReplayKind.SAFE_RESULT,
    datetime(2030, 1, 1, tzinfo=UTC),
)
RESULT = ProjectActionGrantChangeResultDTO(
    InstallationId(UUID(int=5)),
    OrganizationId(UUID(int=4)),
    PROJECT,
    ACTOR,
    RECIPIENT,
    ACTION,
    ProjectActionGrantChangeKind.SET,
    False,
    8,
    True,
    201,
    OPERATION,
)


class MockAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return AccessContextDTO(ACTOR, MockAuthenticationEvidence.browser())


class MockGrantChanger(ProjectGrantChanger):
    def __init__(self) -> None:
        self.result = RESULT
        self.calls: list[
            tuple[
                SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
                IdempotencyContextDTO,
            ]
        ] = []
        self.closed = 0
        self.error: Exception | None = None

    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: IdempotencyContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        raise NotImplementedError

    @override
    async def set_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def remove_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return replace(self.result, change_kind="remove", can_grant=None, status_code=200)


def _client(changer: MockGrantChanger) -> TestClient:
    @asynccontextmanager
    async def open_changer() -> AsyncGenerator[ProjectGrantChanger]:
        try:
            yield changer
        finally:
            changer.closed += 1

    app = FastAPI()
    register_error_handlers(app)
    auth = MockAuthentication()
    app.include_router(
        create_project_action_grant_change_router(
            HumanSessionDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
            ),
            open_changer,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("status,changed", [(201, True), (200, True), (200, False)])
def test_put_preserves_original_status_level_revision_and_expiry(
    status: int, changed: bool
) -> None:
    changer = MockGrantChanger()
    changer.result = replace(
        RESULT, status_code=status, changed=changed, access_revision=7 + int(changed)
    )
    with _client(changer) as client:
        response = client.put(
            ROUTE, json={"canGrant": False, "expectedAccessRevision": 7}, headers=HEADERS
        )
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "operationId": "original-grant",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
        "projectId": str(PROJECT.value),
        "recipientPrincipalId": str(RECIPIENT.value),
        "actionId": ACTION.value,
        "canGrant": False,
        "accessRevision": 7 + int(changed),
        "changed": changed,
    }
    command, context = changer.calls[0]
    assert command == SetProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, False, 7)
    assert (context.method, context.requested_route, context.key.value) == (
        "PUT",
        ROUTE,
        "grant-bob",
    )
    assert changer.closed == 1


@pytest.mark.parametrize("changed", [True, False])
def test_delete_is_bodyless_and_returns_original_removal(changed: bool) -> None:
    changer = MockGrantChanger()
    changer.result = replace(RESULT, changed=changed, access_revision=7 + int(changed))
    with _client(changer) as client:
        response = client.delete(ROUTE + "?expectedAccessRevision=7", headers=HEADERS)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["removed"] is True and "canGrant" not in response.json()
    assert response.json()["changed"] is changed
    command, context = changer.calls[0]
    assert command == RemoveProjectActionGrantCommand(PROJECT, RECIPIENT, ACTION, 7)
    assert (context.method, context.requested_route) == ("DELETE", ROUTE)


@pytest.mark.parametrize(
    "body",
    [
        {"canGrant": "false", "expectedAccessRevision": 7},
        {"canGrant": 0, "expectedAccessRevision": 7},
        {"canGrant": False, "expectedAccessRevision": True},
        {"canGrant": False, "expectedAccessRevision": -1},
        {"canGrant": False, "expectedAccessRevision": 2**63},
        {"canGrant": False, "expectedAccessRevision": 7, "extra": True},
    ],
)
def test_invalid_put_never_opens_the_mutation(body: dict[str, object]) -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        response = client.put(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert changer.calls == [] and changer.closed == 0


@pytest.mark.parametrize(
    "revision", ["", "-1", "+1", "01", "0" * 20, "1.0", "1e0", " 1", "١", str(2**63)]
)
def test_delete_requires_one_canonical_signed_bigint_revision(revision: str) -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        response = client.delete(
            ROUTE, params={"expectedAccessRevision": revision}, headers=HEADERS
        )
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"
    assert changer.calls == [] and changer.closed == 0


@pytest.mark.parametrize(
    "body",
    [
        '{"canGrant":false,"canGrant":true,"expectedAccessRevision":7}',
        '{"canGrant":false,"expectedAccessRevision":7,"expectedAccessRevision":8}',
    ],
)
def test_duplicate_json_fields_are_rejected(body: str) -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        response = client.put(
            ROUTE, content=body, headers=HEADERS | {"Content-Type": "application/json"}
        )
    assert (
        response.status_code == 422
        and response.json()["code"] == "invalid_input"
        and changer.calls == []
    )


@pytest.mark.parametrize(
    "query",
    ["expectedAccessRevision=7&expectedAccessRevision=7", "expectedAccessRevision=7&extra=1"],
)
def test_delete_cannot_hide_ambiguous_inputs(query: str) -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        response = client.delete(ROUTE + "?" + query, headers=HEADERS)
    assert response.status_code == 422 and changer.calls == []


def test_delete_rejects_json_body_and_cookie_write_requires_csrf() -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        body = client.request(
            "DELETE", ROUTE + "?expectedAccessRevision=7", content=b"{}", headers=HEADERS
        )
        denied = client.put(
            ROUTE,
            json={"canGrant": False, "expectedAccessRevision": 7},
            headers={k: v for k, v in HEADERS.items() if k != "X-Inframeld-CSRF"},
        )
    assert body.status_code == 422 and denied.status_code == 403 and changer.calls == []


@pytest.mark.parametrize(
    "size,media,status", [(32769, "application/json", 413), (2, "text/plain", 415)]
)
def test_bounded_body_profile_rejects_before_mutation(size: int, media: str, status: int) -> None:
    changer = MockGrantChanger()
    with _client(changer) as client:
        response = client.put(ROUTE, content=b"x" * size, headers=HEADERS | {"Content-Type": media})
    assert response.status_code == status and response.json()["code"] == "http_error"
    assert response.headers["cache-control"] == "no-store" and changer.calls == []


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AccessDeniedError(), 403, "access_denied"),
        (ResourceNotFoundError(), 404, "resource_not_found"),
        (ConflictError(), 409, "conflict"),
        (InvalidInputError(), 422, "invalid_input"),
        (DependencyUnavailableError(), 503, "dependency_unavailable"),
    ],
)
def test_typed_problems_close_the_request_lifetime(
    error: Exception, status: int, code: str
) -> None:
    changer = MockGrantChanger()
    changer.error = error
    with _client(changer) as client:
        response = client.put(
            ROUTE, json={"canGrant": False, "expectedAccessRevision": 7}, headers=HEADERS
        )
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == code
    assert response.headers["content-type"] == "application/problem+json"
    assert changer.closed == 1


@pytest.mark.parametrize("public_json", [False, True], ids=["native", "serialized"])
def test_registered_contract_keeps_exact_numeric_bounds_and_delete_query_only(
    public_json: bool,
) -> None:
    application = create_app()
    schema = (
        TestClient(application).get("/v1/openapi.json").json()
        if public_json
        else application.openapi()
    )
    schemas = schema["components"]["schemas"]
    for name, field in (
        ("ProjectActionGrantRequest", "expectedAccessRevision"),
        ("ProjectActionGrantResponse", "accessRevision"),
        ("ProjectActionGrantRemovalResponse", "accessRevision"),
        ("MyProjectAccessResponse", "accessRevision"),
    ):
        revision = schemas[name]["properties"][field]
        assert type(revision["minimum"]) is int and revision["minimum"] == 0
        assert type(revision["maximum"]) is int and revision["maximum"] == 2**63 - 1
    path = schema["paths"]["/v1/projects/{project_id}/grants/{recipient_principal_id}/{action_id}"]
    assert path["put"]["operationId"] == "setProjectActionGrant"
    assert set(schemas["ProjectActionGrantRequest"]["required"]) == {
        "canGrant",
        "expectedAccessRevision",
    }
    assert schemas["ProjectActionGrantRequest"]["additionalProperties"] is False
    assert (
        path["delete"]["operationId"] == "removeProjectActionGrant"
        and "requestBody" not in path["delete"]
    )
    revision = next(
        value for value in path["delete"]["parameters"] if value["name"] == "expectedAccessRevision"
    )
    assert revision["in"] == "query" and revision["required"] is True
    assert type(revision["schema"]["maximum"]) is int and revision["schema"]["maximum"] == 2**63 - 1
    own = schema["paths"]["/v1/projects/{project_id}/my-access"]["get"]
    assert own["operationId"] == "getMyProjectAccess"
