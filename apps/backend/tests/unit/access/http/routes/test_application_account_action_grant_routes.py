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
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_action_grant_dto import (
    ApplicationAccountActionGrantDTO,
)
from inframeld_backend.access.application.dtos.application_account_action_grants_page_dto import (
    ApplicationAccountActionGrantsPageDTO,
)
from inframeld_backend.access.application.protocols.application_account_action_grant_changer import (
    ApplicationAccountActionGrantChanger,
)
from inframeld_backend.access.application.protocols.application_account_action_grants_reader import (
    ApplicationAccountActionGrantsReader,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.queries.list_application_account_action_grants_query import (
    ListApplicationAccountActionGrantsQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.application_account_action_grant_routes import (
    create_application_account_action_grant_router,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
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
ACTION = ActionId("issue-application-keys")
ORGANIZATION = OrganizationId(UUID(int=4))
GROUP = AccessGroupId(UUID(int=6))
APPLICATION = PrincipalId(UUID(int=7))
BASE = f"/v1/projects/{PROJECT.value}/application-accounts/{APPLICATION.value}/grants"
ROUTE = BASE + f"/{RECIPIENT.value}/{ACTION.value}"
HEADERS = {
    "Cookie": "ory_kratos_session=controlled",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "grant-bob",
}
OPERATION = CompletedSynchronousOperationDTO(
    operation_id=OperationId("original-grant"),
    created=False,
    replay_kind=OperationReplayKind.SAFE_RESULT,
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
)
RESULT = ApplicationAccountActionGrantChangeResultDTO(
    installation_id=InstallationId(UUID(int=5)),
    organization_id=OrganizationId(UUID(int=4)),
    project_id=PROJECT,
    application_principal_id=APPLICATION,
    actor_principal_id=ACTOR,
    recipient_principal_id=RECIPIENT,
    action_id=ACTION,
    method=HttpMethod.PUT,
    can_grant=False,
    access_revision=8,
    changed=True,
    status_code=201,
    operation=OPERATION,
)


class MockAuthentication(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return AccessContextDTO(ACTOR, MockAuthenticationEvidence.browser())


class MockGrantChanger(ApplicationAccountActionGrantChanger):
    def __init__(self) -> None:
        self.result = RESULT
        self.calls: list[
            tuple[
                SetApplicationAccountActionGrantCommand
                | RemoveApplicationAccountActionGrantCommand,
                IdempotencyContextDTO,
            ]
        ] = []
        self.closed = 0
        self.error: Exception | None = None

    @override
    async def set_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def remove_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        self.calls.append((command, context))
        if self.error is not None:
            raise self.error
        return replace(self.result, method=HttpMethod.DELETE, can_grant=None, status_code=200)


class MockGrantsReader(ApplicationAccountActionGrantsReader):
    def __init__(self) -> None:
        self.calls: list[ListApplicationAccountActionGrantsQuery] = []
        self.closed = 0
        self.error: Exception | None = None

    @override
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListApplicationAccountActionGrantsQuery
    ) -> ApplicationAccountActionGrantsPageDTO:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return ApplicationAccountActionGrantsPageDTO(
            project_id=PROJECT,
            application_principal_id=APPLICATION,
            action_id=ACTION,
            items=(
                ApplicationAccountActionGrantDTO(
                    recipient_principal_id=RECIPIENT, action_id=ACTION, can_grant=False
                ),
            ),
            next_cursor="opaque_cursor",
        )


def _client(changer: MockGrantChanger, reader: MockGrantsReader | None = None) -> TestClient:
    reader = reader or MockGrantsReader()

    @asynccontextmanager
    async def open_changer() -> AsyncGenerator[ApplicationAccountActionGrantChanger]:
        try:
            yield changer
        finally:
            changer.closed += 1

    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ApplicationAccountActionGrantsReader]:
        try:
            yield reader
        finally:
            reader.closed += 1

    app = FastAPI()
    register_error_handlers(app)
    auth = MockAuthentication()
    app.include_router(
        create_application_account_action_grant_router(
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
            open_changer,
            open_reader,
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
        "applicationPrincipalId": str(APPLICATION.value),
        "recipientPrincipalId": str(RECIPIENT.value),
        "actionId": ACTION.value,
        "canGrant": False,
        "accessRevision": 7 + int(changed),
        "changed": changed,
    }
    command, context = changer.calls[0]
    assert command == SetApplicationAccountActionGrantCommand(
        project_id=PROJECT,
        application_principal_id=APPLICATION,
        recipient_principal_id=RECIPIENT,
        action_id=ACTION,
        can_grant=False,
        expected_access_revision=7,
    )
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
    assert command == RemoveApplicationAccountActionGrantCommand(
        project_id=PROJECT,
        application_principal_id=APPLICATION,
        recipient_principal_id=RECIPIENT,
        action_id=ACTION,
        expected_access_revision=7,
    )
    assert (context.method, context.requested_route) == ("DELETE", ROUTE)


@pytest.mark.parametrize(
    "body",
    [
        {"canGrant": "false", "expectedAccessRevision": 7},
        {"canGrant": 0, "expectedAccessRevision": 7},
        {"canGrant": False, "expectedAccessRevision": True},
        {"canGrant": False, "expectedAccessRevision": -1},
        {"canGrant": False, "expectedAccessRevision": 2**53},
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
    "revision", ["", "-1", "+1", "01", "0" * 20, "1.0", "1e0", " 1", "١", str(2**53)]
)
def test_delete_requires_one_canonical_safe_integer_revision(revision: str) -> None:
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


def test_get_maps_bounded_stored_page_without_write_context() -> None:
    reader = MockGrantsReader()
    with _client(MockGrantChanger(), reader) as client:
        response = client.get(
            BASE,
            params={"actionId": ACTION.value, "limit": 2, "cursor": "opaque_cursor"},
            headers={"Authorization": "Bearer controlled"},
        )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "projectId": str(PROJECT.value),
                "applicationPrincipalId": str(APPLICATION.value),
                "recipientPrincipalId": str(RECIPIENT.value),
                "actionId": ACTION.value,
                "canGrant": False,
            }
        ],
        "nextCursor": "opaque_cursor",
    }
    assert (
        len(reader.calls) == 1
        and reader.calls[0].limit == 2
        and reader.calls[0].cursor == "opaque_cursor"
    )
    assert reader.closed == 1


def test_put_accepts_explicit_delegating_level() -> None:
    changer = MockGrantChanger()
    changer.result = replace(RESULT, can_grant=True)
    with _client(changer) as client:
        response = client.put(
            ROUTE, json={"canGrant": True, "expectedAccessRevision": 7}, headers=HEADERS
        )
    assert response.status_code == 201 and response.json()["canGrant"] is True
    assert len(changer.calls) == 1
    command = changer.calls[0][0]
    assert (
        isinstance(command, SetApplicationAccountActionGrantCommand) and command.can_grant is True
    )
