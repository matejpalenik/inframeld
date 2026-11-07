from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.application_key_dependency import (
    ApplicationKeyDependency,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers


def test_application_identity_route_rejects_human_families_before_verification() -> None:
    auth = MockApplicationAuthenticator(
        AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.application_key())
    )
    app = FastAPI()
    register_error_handlers(app)
    dependency = ApplicationKeyDependency(auth)

    @app.get("/identity")
    async def identity(access: Annotated[AccessContextDTO, Depends(dependency)]) -> str:
        return str(access.actor_principal_id.value)

    with TestClient(app) as client:
        assert (
            client.get("/identity", headers={"Authorization": "Bearer human-opaque"}).status_code
            == 401
        )
        assert (
            client.get("/identity", headers={"Cookie": "ory_kratos_session=cookie"}).status_code
            == 401
        )
        assert client.get("/identity").status_code == 401
    assert auth.calls == 0
