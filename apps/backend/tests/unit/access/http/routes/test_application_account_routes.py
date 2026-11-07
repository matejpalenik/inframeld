"""Exercise account wire meaning, strict parsing and cookie protection through real routes."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import ACCESS, SAVED_RESULT

from inframeld_backend.access.application.commands.create_application_account_command import (
    CreateApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_page_dto import (
    ApplicationKeysPageDTO,
)
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.protocols.application_account_creator import (
    ApplicationAccountCreator,
)
from inframeld_backend.access.application.protocols.application_account_reader import (
    ApplicationAccountReader,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.application_account_routes import (
    create_application_account_router,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

PROJECT = ProjectId(UUID(int=3))
APP = PrincipalId(UUID(int=8))
KEY = ApplicationKeyId(UUID(int=10))
ROUTE = f"/v1/projects/{PROJECT.value}/application-accounts"
BODY = {"name": "support-bot", "displayName": "SupportBot", "expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "create-original",
}


class MockAccountOperations(ApplicationAccountCreator, ApplicationAccountReader):
    def __init__(self) -> None:
        self.commands: list[CreateApplicationAccountCommand] = []
        self.context: IdempotencyContextDTO | None = None
        self.reads: list[object] = []
        self.metadata = ApplicationAccountMetadataDTO(
            OrganizationId(UUID(int=2)),
            PROJECT,
            APP,
            ResourceName("support-bot"),
            "SupportBot",
            PrincipalStatus.ACTIVE,
            SAVED_RESULT.expires_at,
            8,
        )
        self.key = ApplicationKeyMetadataDTO(
            KEY,
            APP,
            PROJECT,
            (ApplicationKeyAdapter.HTTP,),
            SAVED_RESULT.expires_at,
            SAVED_RESULT.expires_at,
            None,
        )

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountCreationResultDTO:
        self.commands.append(command)
        self.context = context
        return ApplicationAccountCreationResultDTO(
            CreatedApplicationAccountDTO(
                SAVED_RESULT.operation_id,
                self.metadata.organization_id,
                PROJECT,
                APP,
                ACCESS.actor_principal_id,
                command.name,
                command.display_name.value,
                8,
                tuple(
                    ActionId(a)
                    for a in (
                        "issue-application-keys",
                        "revoke-application-keys",
                        "delete-application-account",
                    )
                ),
            ),
            replace(SAVED_RESULT, created=True),
        )

    @override
    async def get_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, principal_id: PrincipalId
    ) -> ApplicationAccountMetadataDTO:
        self.reads.append((project_id, principal_id))
        return self.metadata

    @override
    async def resolve_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, name: ResourceName
    ) -> ApplicationAccountMetadataDTO:
        self.reads.append((project_id, name))
        return self.metadata

    @override
    async def list_keys(
        self, *, access: AccessContextDTO, query: ListApplicationKeysQuery
    ) -> ApplicationKeysPageDTO:
        self.reads.append(query)
        return ApplicationKeysPageDTO((self.key,), None)

    @override
    async def get_key(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId,
    ) -> ApplicationKeyMetadataDTO:
        self.reads.append((project_id, application_principal_id, key_id))
        return self.key


class MockAccountAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return AccessContextDTO(ACCESS.actor_principal_id, MockAuthenticationEvidence.browser())


def client_for(service: MockAccountOperations) -> TestClient:
    @asynccontextmanager
    async def open_operation() -> AsyncGenerator[MockAccountOperations]:
        yield service

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    authenticate = MockAccountAuthenticator()
    app.include_router(
        create_application_account_router(
            ProductAccessDependency(
                authenticate,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=authenticate,
                application_authenticator=MockApplicationAuthenticator(
                    AccessContextDTO(
                        PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
                    ),
                    failure=AuthenticationRequiredError(),
                ),
            ),
            open_operation,
            open_operation,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


def test_creation_returns_one_principal_and_exact_historical_creator_receipt() -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert body["principalId"] == str(APP.value) and body["projectId"] == str(PROJECT.value)
    assert body["name"] == "support-bot" and body["accessRevision"] == 8
    assert [(g["actionId"], g["canGrant"], g["target"]) for g in body["initialGrants"]] == [
        (
            a,
            True,
            {
                "kind": "application-account",
                "projectId": str(PROJECT.value),
                "applicationPrincipalId": str(APP.value),
            },
        )
        for a in ("issue-application-keys", "revoke-application-keys", "delete-application-account")
    ]
    assert service.context is not None and service.context.requested_route == ROUTE
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        f"/{APP.value}",
        "/resolve?name=support-bot",
        f"/{APP.value}/keys",
        f"/{APP.value}/keys/{KEY.value}",
    ],
)
def test_metadata_reads_use_typed_routes_without_secret_fields(path: str) -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.get(ROUTE + path, headers={"Authorization": "Bearer controlled-token"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "verifier" not in response.text and "secret" not in response.text
    assert len(service.reads) == 1


@pytest.mark.parametrize("value", [True, 1.0, "7", -1, 9007199254740992])
def test_creation_rejects_inexact_revisions_without_invoking_operation(value: object) -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.post(
            ROUTE, json={**BODY, "expectedAccessRevision": value}, headers=HEADERS
        )
    assert response.status_code == 422 and not service.commands


@pytest.mark.parametrize(
    "body",
    [{**BODY, "unknown": 1}, {**BODY, "name": "SupportBot"}, {**BODY, "displayName": " padded "}],
)
def test_creation_rejects_unknown_fields_and_unaccepted_names(body: dict[str, object]) -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.post(ROUTE, json=body, headers=HEADERS)
    assert response.status_code == 422 and not service.commands


@pytest.mark.parametrize(
    "raw",
    [
        '{"name":"a","name":"b","displayName":"Bot","expectedAccessRevision":7}',
        '{"name":"a","displayName":"Bot","expectedAccessRevision":NaN}',
        "[]",
    ],
)
def test_creation_rejects_ambiguous_json(raw: str) -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.post(
            ROUTE, content=raw, headers={**HEADERS, "Content-Type": "application/json"}
        )
    assert (
        response.status_code == 422
        and response.json()["code"] == "invalid_input"
        and not service.commands
    )


def test_cookie_creation_needs_csrf_and_bearer_creation_does_not() -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        denied = client.post(
            ROUTE, json=BODY, headers={"Cookie": HEADERS["Cookie"], "Idempotency-Key": "original"}
        )
        allowed = client.post(
            ROUTE,
            json=BODY,
            headers={"Authorization": "Bearer controlled-token", "Idempotency-Key": "original"},
        )
    assert denied.status_code == 403 and allowed.status_code == 201
    assert len(service.commands) == 1


@pytest.mark.parametrize("query", ["limit=1.0", "limit=1&limit=2", "cursor=a&cursor=b", "other=1"])
def test_key_list_rejects_ambiguous_or_inexact_query(query: str) -> None:
    service = MockAccountOperations()
    with client_for(service) as client:
        response = client.get(
            f"{ROUTE}/{APP.value}/keys?{query}",
            headers={"Authorization": "Bearer controlled-token"},
        )
    assert (
        response.status_code == 422
        and response.json()["code"] == "invalid_input"
        and not service.reads
    )
