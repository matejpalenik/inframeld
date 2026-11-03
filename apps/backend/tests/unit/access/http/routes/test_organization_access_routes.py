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
from inframeld_backend.access.application.dtos.my_organization_access_dto import (
    MyOrganizationAccessDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.my_organization_access_reader import (
    MyOrganizationAccessReader,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.organization_access_routes import (
    create_organization_access_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())


class MockOwnAccessAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
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


class MockOwnAccessReader(MyOrganizationAccessReader):
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    @override
    async def read(self, *, access: AccessContextDTO) -> MyOrganizationAccessDTO:
        self.calls += 1
        assert access.actor_principal_id == ACCESS.actor_principal_id
        if self.error:
            raise self.error
        return MyOrganizationAccessDTO(
            OrganizationId(UUID(int=2)), access.actor_principal_id, 7, ()
        )


def client_for(
    reader: MockOwnAccessReader, authenticator: MockOwnAccessAuthenticator
) -> TestClient:
    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[MockOwnAccessReader]:
        yield reader

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    app.include_router(
        create_organization_access_router(
            HumanSessionDependency(
                authenticator,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=authenticator,
            ),
            open_reader,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app)


@pytest.mark.parametrize(
    "headers",
    [
        {"Cookie": "ory_kratos_session=controlled-cookie"},
        {"Authorization": "Bearer controlled-token"},
    ],
)
def test_current_human_observes_empty_own_access_without_create_permission(
    headers: dict[str, str],
) -> None:
    reader, authenticator = MockOwnAccessReader(), MockOwnAccessAuthenticator()
    with client_for(reader, authenticator) as client:
        response = client.get("/v1/my-organization-access", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "organizationId": str(UUID(int=2)),
        "principalId": str(UUID(int=1)),
        "accessRevision": 7,
        "grants": [],
    }
    assert response.headers["cache-control"] == "no-store"
    assert reader.calls == authenticator.calls == 1


def test_unsupported_application_key_is_not_a_claimed_http_authentication_path() -> None:
    reader, authenticator = MockOwnAccessReader(), MockOwnAccessAuthenticator()
    with client_for(reader, authenticator) as client:
        response = client.get(
            "/v1/my-organization-access", headers={"Authorization": "Bearer ifm_app_controlled"}
        )
    assert response.status_code == 401
    assert reader.calls == authenticator.calls == 0


def test_current_service_denial_is_private_and_no_store() -> None:
    reader, authenticator = MockOwnAccessReader(), MockOwnAccessAuthenticator()
    reader.error = AccessDeniedError()
    with client_for(reader, authenticator) as client:
        response = client.get(
            "/v1/my-organization-access", headers={"Authorization": "Bearer controlled-token"}
        )
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert response.headers["cache-control"] == "no-store"
