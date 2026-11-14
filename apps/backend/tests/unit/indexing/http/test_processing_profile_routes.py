from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    PROJECT_ID,
    MockOperationIdempotency,
    MockTransactions,
)
from tests.unit.access.http.routes.test_application_account_routes import MockAccountAuthenticator
from tests.unit.indexing.application.services.test_processing_profile_creation_service import (
    COMMAND,
    FACTS,
    MockCreationRepository,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.protocols.processing_profile_read_repository import (
    ProcessingProfileReadRepository,
)
from inframeld_backend.indexing.application.services.processing_profile_creation_service import (
    ProcessingProfileCreationService,
)
from inframeld_backend.indexing.application.services.processing_profile_read_service import (
    ProcessingProfileReadService,
)
from inframeld_backend.indexing.application.value_objects.processing_profiles_cursor import (
    ProcessingProfilesCursor,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.http.responses.processing_profile_creation_response import (
    ProcessingProfileCreationResponse,
)
from inframeld_backend.indexing.http.routes.processing_profile_routes import (
    create_processing_profile_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ROUTE = f"/v1/projects/{PROJECT_ID.value}/processing-profiles"
DEFINITION = {
    "doclingSlimVersion": COMMAND.definition.docling_slim_version,
    "doclingCoreVersion": COMMAND.definition.docling_core_version,
    "assetManifestSha256": COMMAND.definition.asset_manifest_sha256,
    "maxContentTokens": COMMAND.definition.max_content_tokens,
    "mergePeers": COMMAND.definition.merge_peers,
    "repeatTableHeader": COMMAND.definition.repeat_table_header,
    "ocrEnabled": False,
}
BODY = {
    "name": COMMAND.name.value,
    "displayName": COMMAND.display_name.value,
    "definition": DEFINITION,
}
HEADERS = {
    "Authorization": "Bearer human-access-token",
    "Idempotency-Key": "processing-profile-create",
}


INSTALLATION = InstallationId(UUID(int=11))
FIRST = ProcessingProfileDTO(
    project_id=PROJECT_ID,
    id=ProcessingProfileId(UUID(int=1)),
    name=COMMAND.name,
    display_name=COMMAND.display_name,
    definition=COMMAND.definition,
)
NEXT = replace(FIRST, id=ProcessingProfileId(UUID(int=2)))


class MockReadRepository(ProcessingProfileReadRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = FACTS.action

    @override
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO]:
        self.events.append("scope")
        assert access == ACCESS and project_id == PROJECT_ID
        return INSTALLATION, self.facts

    @override
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: ProcessingProfileId
    ) -> ProcessingProfileDTO | None:
        self.events.append("get")
        assert facts == self.facts and project_id == PROJECT_ID
        return FIRST if profile_id == FIRST.id else None

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ProcessingProfileId | None,
        limit: int,
    ) -> tuple[ProcessingProfileDTO, ...]:
        self.events.append("list")
        assert facts == self.facts and project_id == PROJECT_ID and limit == 2
        return (FIRST, NEXT) if after is None else (NEXT,)


def _client(events: list[str], read_repository: MockReadRepository | None = None) -> TestClient:
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION

    @asynccontextmanager
    async def open_creation() -> AsyncGenerator[ProcessingProfileCreationService]:
        yield ProcessingProfileCreationService(
            MockCreationRepository(events),
            idempotency,
            RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
            transactions=MockTransactions(events),
        )

    @asynccontextmanager
    async def open_reader() -> AsyncGenerator[ProcessingProfileReadService]:
        yield ProcessingProfileReadService(
            MockTransactions(events), read_repository or MockReadRepository(events)
        )

    auth = MockAccountAuthenticator()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_processing_profile_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(
                    ACCESS, failure=AuthenticationRequiredError()
                ),
            ),
            open_creation,
            open_reader,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    configure_problem_openapi(app, serialization_models=(ProcessingProfileCreationResponse,))
    return TestClient(app)


def test_create_returns_the_exact_definition_and_delegable_creator_grants() -> None:
    events: list[str] = []
    with _client(events) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
        description = client.get("/openapi.json").json()["paths"]

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    collection = description["/v1/projects/{project_id}/processing-profiles"]
    assert collection["post"]["operationId"] == "createProcessingProfile"
    assert collection["get"]["operationId"] == "listProcessingProfiles"
    assert (
        description["/v1/projects/{project_id}/processing-profiles/{processing_profile_id}"]["get"][
            "operationId"
        ]
        == "getProcessingProfile"
    )
    result = response.json()
    profile = result["profile"]
    assert profile["projectId"] == str(PROJECT_ID.value)
    assert UUID(profile["processingProfileId"])
    assert {key: profile[key] for key in BODY} == BODY
    assert result["projectAccessRevision"] == 8
    assert result["initialGrants"] == [
        {
            "target": {
                "kind": "processing-profile",
                "processingProfileId": profile["processingProfileId"],
            },
            "actionId": action,
            "canGrant": True,
        }
        for action in ("view-processing-profile", "use-processing-profile")
    ]
    assert events == ["begin", "authority", "reserve", "save", "complete", "commit"]


def test_rejects_ambiguous_json_unsupported_settings_and_coercion_before_creation() -> None:
    events: list[str] = []
    with _client(events) as client:
        duplicate = client.post(
            ROUTE,
            content='{"definition":{"mergePeers":true,"mergePeers":false}}',
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        media = client.post(ROUTE, content="name = 'handbook'", headers=HEADERS)
        missing_key = client.post(
            ROUTE, json=BODY, headers={"Authorization": HEADERS["Authorization"]}
        )
        invalid = [
            client.post(
                ROUTE,
                json={**BODY, "definition": {**DEFINITION, **fields}},
                headers=HEADERS,
            )
            for fields in (
                {"ocrEnabled": 0},
                {"mergePeers": 1},
                {"maxContentTokens": 4.0},
                {"assetManifestSha256": "f" * 64},
                {"assetPath": "private-sentinel"},
            )
        ]
    assert duplicate.status_code == 422 and duplicate.json()["code"] == "invalid_input"
    assert media.status_code == 415
    assert missing_key.status_code == 422
    assert all(response.status_code == 422 for response in invalid)
    assert all("private-sentinel" not in response.text for response in invalid)
    assert not events


def test_get_and_list_scope_each_request_and_return_one_bounded_page() -> None:
    events: list[str] = []
    with _client(events) as client:
        item = client.get(f"{ROUTE}/{FIRST.id.value}", headers=HEADERS)
        first = client.get(ROUTE, params={"limit": 1}, headers=HEADERS)
        assert first.status_code == 200
        following = client.get(
            ROUTE, params={"limit": 1, "cursor": first.json()["nextCursor"]}, headers=HEADERS
        )

    assert item.status_code == 200 and item.json() == first.json()["items"][0]
    assert item.headers["cache-control"] == "no-store"
    assert first.json()["items"] == [item.json()]
    assert following.status_code == 200
    assert [profile["processingProfileId"] for profile in following.json()["items"]] == [
        str(NEXT.id.value)
    ]
    assert following.json()["nextCursor"] is None
    assert events == ["begin", "scope", "get", "commit"] + ["begin", "scope", "list", "commit"] * 2


def test_bad_scope_and_ungranted_detail_do_not_disclose_a_profile() -> None:
    events: list[str] = []
    repository = MockReadRepository(events)
    wrong_cursor = ProcessingProfilesCursor(
        INSTALLATION, ProjectId(UUID(int=900)), FIRST.id
    ).to_token()
    with _client(events, repository) as client:
        missing = client.get(f"{ROUTE}/{NEXT.id.value}", headers=HEADERS)
        incompatible = client.get(
            ROUTE, params={"limit": 1, "cursor": wrong_cursor}, headers=HEADERS
        )
        duplicate = client.get(f"{ROUTE}?limit=1&limit=2", headers=HEADERS)
        unexpected = client.get(f"{ROUTE}/{FIRST.id.value}?limit=1", headers=HEADERS)
        repository.facts = replace(repository.facts, is_project_member=False)
        hidden = client.get(ROUTE, params={"limit": 1}, headers=HEADERS)

    assert missing.status_code == hidden.status_code == 404
    assert all(
        response.status_code == 422 and response.json()["code"] == "invalid_input"
        for response in (incompatible, duplicate, unexpected)
    )
    assert events == ["begin", "scope", "get", "rollback"] + ["begin", "scope", "rollback"] * 2
