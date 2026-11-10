"""Qualify exact deletion transport and safe original admission without a database."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_deleter import ProjectDeleter
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.responses.project_deletion_admission_response import (
    ProjectDeletionAdmissionResponse,
)
from inframeld_backend.access.http.routes.project_deletion_routes import (
    create_project_deletion_router,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

PROJECT = ProjectId(UUID(int=3))
ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
PATH = f"/v1/projects/{PROJECT.value}"
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "delete-original",
}


class MockAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        if credential is None:
            raise AuthenticationRequiredError()
        return ACCESS


class MockDeleter(ProjectDeleter):
    def __init__(self) -> None:
        self.commands: list[DeleteProjectCommand] = []
        self.contexts: list[IdempotencyContextDTO] = []
        self.requests: list[RequestId] = []
        self.failure: Exception | None = None

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> ProjectDeletionResultDTO:
        assert access == ACCESS
        self.commands.append(command)
        self.contexts.append(context)
        self.requests.append(request_id)
        if self.failure is not None:
            raise self.failure
        return ProjectDeletionResultDTO(
            InstallationId(UUID(int=2)),
            OrganizationId(UUID(int=4)),
            command.project_id,
            access.actor_principal_id,
            ProjectDeletionObligationId(UUID(int=5)),
            JobId(UUID(int=6)),
            7,
            8,
            AcceptedAsyncOperationDTO(OperationId("original-delete"), False, None),
        )


def client_for(service: MockDeleter) -> TestClient:
    @asynccontextmanager
    async def open_deleter() -> AsyncGenerator[ProjectDeleter]:
        yield service

    auth = MockAuthenticator()
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(
        create_project_deletion_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(
                    ACCESS, failure=AuthenticationRequiredError()
                ),
            ),
            open_deleter,
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def test_delete_returns_only_original_six_field_acceptance() -> None:
    service = MockDeleter()
    with client_for(service) as client:
        response = client.delete(PATH + "?expectedAccessRevision=7", headers=HEADERS)
    assert response.status_code == 202
    assert response.json() == {
        "operationId": "original-delete",
        "idempotencyExpiresAt": None,
        "projectId": str(PROJECT.value),
        "accessRevision": 8,
        "admissionConfirmed": True,
        "accessBlocked": True,
    }
    assert response.headers["cache-control"] == "no-store"
    assert service.commands == [DeleteProjectCommand(PROJECT, 7)]
    assert service.contexts[0].requested_route == PATH
    assert service.contexts[0].key.value == HEADERS["Idempotency-Key"]
    assert len(service.requests) == 1


@pytest.mark.parametrize(
    "query",
    [
        "",
        "expectedAccessRevision=7&expectedAccessRevision=7",
        "expectedAccessRevision=07",
        "expectedAccessRevision=-1",
        "expectedAccessRevision=+7",
        "expectedAccessRevision=7.0",
        "expectedAccessRevision=1e2",
        "expectedAccessRevision=true",
        "expectedAccessRevision=9007199254740992",
        "expectedAccessRevision=7&other=secret",
    ],
)
def test_ambiguous_revision_is_rejected_before_admission(query: str) -> None:
    service = MockDeleter()
    with client_for(service) as client:
        response = client.delete(PATH + "?" + query, headers=HEADERS)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert service.commands == []


@pytest.mark.parametrize("body", [b"{}", b" ", b"secret"])
def test_body_is_rejected_before_admission(body: bytes) -> None:
    service = MockDeleter()
    with client_for(service) as client:
        response = client.request(
            "DELETE", PATH + "?expectedAccessRevision=7", content=body, headers=HEADERS
        )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert service.commands == []


@pytest.mark.parametrize("key", ["", " ", "k" * 129])
def test_invalid_original_key_is_rejected(key: str) -> None:
    service = MockDeleter()
    with client_for(service) as client:
        response = client.delete(
            PATH + "?expectedAccessRevision=7", headers=HEADERS | {"Idempotency-Key": key}
        )
    assert response.status_code == 422
    assert service.commands == []


def test_cookie_requires_current_origin_and_csrf_while_bearer_uses_its_own_contract() -> None:
    service = MockDeleter()
    with client_for(service) as client:
        missing = {k: v for k, v in HEADERS.items() if k != "X-Inframeld-CSRF"}
        assert client.delete(PATH + "?expectedAccessRevision=7", headers=missing).status_code == 403
        assert (
            client.delete(
                PATH + "?expectedAccessRevision=7",
                headers=HEADERS | {"Origin": "https://untrusted.test"},
            ).status_code
            == 403
        )
        assert service.commands == []
        response = client.delete(
            PATH + "?expectedAccessRevision=7",
            headers={
                "Authorization": "Bearer controlled-token",
                "Idempotency-Key": "bearer-original",
            },
        )
    assert response.status_code == 202
    assert len(service.commands) == 1


def test_response_requires_nullable_expiry_and_rejects_extra_or_false_progress() -> None:
    fields: dict[str, object] = {
        "operation_id": "original",
        "idempotency_expires_at": None,
        "project_id": PROJECT.value,
        "access_revision": 8,
        "admission_confirmed": True,
        "access_blocked": True,
    }
    assert ProjectDeletionAdmissionResponse.model_validate(fields).idempotency_expires_at is None
    for invalid in (
        {k: v for k, v in fields.items() if k != "idempotency_expires_at"},
        fields | {"job_id": "private"},
        fields | {"admission_confirmed": False},
        fields | {"access_revision": True},
    ):
        with pytest.raises(ValidationError):
            ProjectDeletionAdmissionResponse.model_validate(invalid)


def test_unavailable_outcome_does_not_redispatch_or_expose_internal_ids() -> None:
    service = MockDeleter()
    service.failure = DependencyUnavailableError()
    with client_for(service) as client:
        response = client.delete(PATH + "?expectedAccessRevision=7", headers=HEADERS)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert len(service.commands) == 1
    assert "jobId" not in response.json() and "obligationId" not in response.json()


def test_duplicate_original_key_is_rejected_before_admission() -> None:
    service = MockDeleter()
    with client_for(service) as client:
        response = client.delete(
            PATH + "?expectedAccessRevision=7",
            headers=list(HEADERS.items()) + [("Idempotency-Key", "other")],
        )
    assert response.status_code == 422
    assert service.commands == []
