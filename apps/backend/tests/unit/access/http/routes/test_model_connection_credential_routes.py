import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import ACCESS, PROJECT_ID, SAVED_RESULT
from tests.unit.access.http.routes.test_application_account_routes import MockAccountAuthenticator

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.application.protocols.model_connection_credential_manager import (
    ModelConnectionCredentialManager,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.model_connection_credential_routes import (
    create_model_connection_credential_router,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

_CONNECTION = ModelConnectionId(UUID(int=745))
_ROUTE = f"/v1/projects/{PROJECT_ID.value}/model-connections/{_CONNECTION.value}/credential"
_HEADERS = {"Authorization": "Bearer human-access-token", "Idempotency-Key": "credential-original"}
_TOKEN = "synthetic-preview-key"
_EMPTY = ModelConnectionCredentialDTO(PROJECT_ID, _CONNECTION, None, 0, False, None)
_SLOT = replace(_EMPTY, credential_id=UUID(int=746), changed_at=datetime(2030, 1, 1, tzinfo=UTC))


class _CredentialManager(ModelConnectionCredentialManager):
    def __init__(self) -> None:
        self.calls: list[tuple[ChangeModelConnectionCredentialCommand, IdempotencyContextDTO]] = []

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionCredentialDTO:
        assert access.actor_principal_id == ACCESS.actor_principal_id
        assert (project_id, connection_id) == (PROJECT_ID, _CONNECTION)
        return _EMPTY

    @override
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionCredentialCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCredentialResultDTO:
        assert access.actor_principal_id == ACCESS.actor_principal_id
        self.calls.append((command, context))
        current = replace(
            _SLOT, revision=command.expected_revision + 1, present=command.value is not None
        )
        return ModelConnectionCredentialResultDTO(
            current, True, replace(SAVED_RESULT, created=len(self.calls) != 2)
        )


def _client(manager: _CredentialManager) -> TestClient:
    @asynccontextmanager
    async def open_manager() -> AsyncGenerator[ModelConnectionCredentialManager]:
        yield manager

    authenticator = MockAccountAuthenticator()
    access = ProductAccessDependency(
        authenticator,
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
        access_token_authenticator=authenticator,
        application_authenticator=MockApplicationAuthenticator(
            ACCESS, failure=AuthenticationRequiredError()
        ),
    )
    application = FastAPI()
    register_error_handlers(application)
    application.include_router(create_model_connection_credential_router(access, open_manager))
    application.add_middleware(RequestContextMiddleware)
    return TestClient(application)


def test_safe_metadata_and_same_key_result_keep_exact_route_and_hide_the_value() -> None:
    manager = _CredentialManager()
    body = {"expectedCredentialRevision": 0, "value": _TOKEN}
    with _client(manager) as client:
        empty = client.get(_ROUTE, headers=_HEADERS)
        saved = client.put(_ROUTE, headers=_HEADERS, json=body)
        recovered = client.put(_ROUTE, headers=_HEADERS, json=body)
        removed = client.delete(_ROUTE, headers=_HEADERS, params={"expectedCredentialRevision": 1})

    assert empty.json() == {
        "projectId": str(PROJECT_ID.value),
        "modelConnectionId": str(_CONNECTION.value),
        "credentialId": None,
        "revision": 0,
        "present": False,
        "changedAt": None,
    }
    assert saved.json()["credential"] == {
        **empty.json(),
        "credentialId": str(_SLOT.credential_id),
        "revision": 1,
        "present": True,
        "changedAt": "2030-01-01T00:00:00Z",
    }
    assert saved.json()["replayed"] is False
    assert recovered.json() == {**saved.json(), "replayed": True}
    assert removed.json()["credential"]["revision"] == 2
    assert removed.json()["credential"]["present"] is False
    assert all(
        response.status_code == 200
        and response.headers["cache-control"] == "no-store"
        and _TOKEN not in response.text
        for response in (empty, saved, recovered, removed)
    )
    assert [item.method.value for _, item in manager.calls] == ["PUT", "PUT", "DELETE"]
    assert all(item.requested_route == _ROUTE for _, item in manager.calls)


def test_secret_validation_clamps_stream_before_parse_and_never_reflects_input() -> None:
    manager = _CredentialManager()
    json_headers = {**_HEADERS, "Content-Type": "application/json"}
    escaped = ('{"expectedCredentialRevision":0,"value":"' + "\\u0078" * 16_384 + '"}').encode()

    with _client(manager) as client:
        boundary = client.put(_ROUTE, headers=json_headers, content=escaped)
        oversized = client.put(
            _ROUTE, headers=json_headers, content=(b"x" * 1024 for _ in range(101))
        )
        duplicate = client.put(
            _ROUTE,
            headers=json_headers,
            content='{"expectedCredentialRevision":0,"value":"first","value":"' + _TOKEN + '"}',
        )
        unsafe = client.put(
            _ROUTE, headers=_HEADERS, json={"expectedCredentialRevision": 0, "value": _TOKEN + "\n"}
        )
        extra = client.put(
            _ROUTE,
            headers=_HEADERS,
            json={"expectedCredentialRevision": 0, "value": _TOKEN, _TOKEN: _TOKEN},
        )
        wrong_format = client.put(_ROUTE, headers=_HEADERS, content=json.dumps({"value": _TOKEN}))
        delete_duplicate = client.delete(
            _ROUTE + "?expectedCredentialRevision=1&expectedCredentialRevision=2", headers=_HEADERS
        )
        delete_body = client.request(
            "DELETE", _ROUTE + "?expectedCredentialRevision=1", headers=_HEADERS, content=_TOKEN
        )
        csrf = client.put(
            _ROUTE,
            headers={
                "Idempotency-Key": "csrf",
                "Cookie": "ory_kratos_session=test",
                "Origin": "https://other.test",
            },
            json={"expectedCredentialRevision": 0, "value": _TOKEN},
        )

    assert boundary.status_code == 200
    assert len(manager.calls) == 1
    assert manager.calls[0][0].value is not None
    assert manager.calls[0][0].value.value == "x" * 16_384
    failures = (
        oversized,
        duplicate,
        unsafe,
        extra,
        wrong_format,
        delete_duplicate,
        delete_body,
        csrf,
    )
    assert [response.status_code for response in failures] == [
        413,
        422,
        422,
        422,
        415,
        422,
        422,
        403,
    ]
    assert all(
        response.headers["cache-control"] == "no-store" and _TOKEN not in response.text
        for response in failures
    )
