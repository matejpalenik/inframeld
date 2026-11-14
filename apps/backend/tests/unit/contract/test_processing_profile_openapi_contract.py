from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_application_session_reader import MockApplicationSessionReader
from tests.support.mock_project_metadata import ACCESS, PROJECT_ID, SAVED_RESULT
from tests.unit.access.http.routes.test_application_account_routes import MockAccountAuthenticator
from tests.unit.indexing.http.test_processing_profile_routes import BODY, FIRST, HEADERS, ROUTE

from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profiles_page_dto import (
    ProcessingProfilesPageDTO,
)
from inframeld_backend.indexing.application.services.processing_profile_creation_service import (
    ProcessingProfileCreationService,
)
from inframeld_backend.indexing.application.services.processing_profile_read_service import (
    ProcessingProfileReadService,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.resources.database import Database

_COLLECTION = "/v1/projects/{project_id}/processing-profiles"
_DETAIL = _COLLECTION + "/{processing_profile_id}"
_GRANTS = "/v1/processing-profiles/{processing_profile_id}/grants"
_ASSIGNMENT = _GRANTS + "/{recipient_principal_id}/{action_id}"


def test_native_production_profile_operations_use_existing_security_and_problem_contract() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    creation = paths[_COLLECTION]["post"]
    listing = paths[_COLLECTION]["get"]
    detail = paths[_DETAIL]["get"]
    assert creation["operationId"] == "createProcessingProfile"
    assert listing["operationId"] == "listProcessingProfiles"
    assert detail["operationId"] == "getProcessingProfile"
    assert paths[_GRANTS]["get"]["operationId"] == "listProcessingProfileActionGrants"
    assert paths[_ASSIGNMENT]["put"]["operationId"] == "setProcessingProfileActionGrant"
    assert paths[_ASSIGNMENT]["delete"]["operationId"] == "removeProcessingProfileActionGrant"
    assert "processing-profile" in schema["components"]["schemas"]["GrantTargetKind"]["enum"]
    for operation in (creation, listing, detail):
        assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
        for status in ("401", "403", "404", "422", "503"):
            assert "application/problem+json" in operation["responses"][status]["content"]
    assert {
        parameter["name"] for parameter in listing["parameters"] if parameter["in"] == "query"
    } == {"limit", "cursor"}


def test_native_profile_definition_and_creation_receipt_preserve_exact_bounds() -> None:
    schema = create_app().openapi()
    models = schema["components"]["schemas"]
    request = models["DoclingProcessingDefinitionRequest"]
    assert request["additionalProperties"] is False
    assert {"maxContentTokens", "mergePeers", "repeatTableHeader", "ocrEnabled"}.issubset(
        request["required"]
    )
    assert request["properties"]["maxContentTokens"]["maximum"] == 1024
    assert request["properties"]["ocrEnabled"]["const"] is False
    receipt = models["ProcessingProfileCreationResponse"]["properties"]
    assert type(receipt["projectAccessRevision"]["maximum"]) is int
    assert receipt["projectAccessRevision"]["maximum"] == RevisionValidation.MAX_VALUE
    assert receipt["initialGrants"]["minItems"] == receipt["initialGrants"]["maxItems"] == 2


@pytest.mark.parametrize("create", [False, True])
def test_profile_routes_report_safe_unavailability_during_database_session_exit(
    monkeypatch: pytest.MonkeyPatch, create: bool
) -> None:
    reached: list[str] = []

    def access_components(*_args: object, **_kwargs: object) -> AccessComponents:
        human = MockAccountAuthenticator()
        application = MockApplicationAuthenticator(ACCESS)
        return AccessComponents(
            authenticator=human,
            kratos_client=None,
            access_token_authenticator=human,
            application_authenticator=application,
            mcp_application_authenticator=application,
            application_session_reader=MockApplicationSessionReader(
                CurrentApplicationSessionDTO(ACCESS.actor_principal_id, PROJECT_ID)
            ),
        )

    @asynccontextmanager
    async def unavailable_session(_database: Database) -> AsyncGenerator[AsyncSession]:
        reached.append("session")
        async with AsyncSession() as session:
            yield session
        reached.append("exit")
        raise OperationalError("private-query", None, OSError("private-driver-error"))

    async def create_profile(
        _service: ProcessingProfileCreationService, **_kwargs: object
    ) -> ProcessingProfileCreationDTO:
        reached.append("create")
        return ProcessingProfileCreationDTO(
            profile=FIRST,
            operation=replace(SAVED_RESULT, created=True),
            project_access_revision=8,
            initial_actions=tuple(ProcessingProfileAction),
            can_grant=True,
        )

    async def list_profiles(
        _service: ProcessingProfileReadService, *_args: object
    ) -> ProcessingProfilesPageDTO:
        reached.append("list")
        return ProcessingProfilesPageDTO((FIRST,), None)

    monkeypatch.setattr(
        "inframeld_backend.bootstrap.application_factory.create_access_components",
        access_components,
    )
    monkeypatch.setattr(Database, "session", unavailable_session)
    monkeypatch.setattr(ProcessingProfileCreationService, "create", create_profile)
    monkeypatch.setattr(ProcessingProfileReadService, "list_profiles", list_profiles)
    client = TestClient(create_app(), raise_server_exceptions=False)
    try:
        response = (
            client.post(ROUTE, json=BODY, headers=HEADERS)
            if create
            else client.get(ROUTE, headers=HEADERS)
        )
    finally:
        client.close()
    assert reached == ["session", "create" if create else "list", "exit"]
    assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
    assert "private-query" not in response.text
    assert "private-driver-error" not in response.text
