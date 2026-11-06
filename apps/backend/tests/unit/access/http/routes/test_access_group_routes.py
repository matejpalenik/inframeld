"""Exercise native group requests, original receipts and strict transport boundaries."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID, PROJECT_ID, SAVED_RESULT

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principals_page_dto import (
    AccessGroupPrincipalsPageDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.protocols.access_group_creator import AccessGroupCreator
from inframeld_backend.access.application.protocols.access_group_deleter import AccessGroupDeleter
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.protocols.access_group_relationship_changer import (
    AccessGroupRelationshipChanger,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.access_group_routes import create_access_group_router
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

GROUP = AccessGroupId(UUID(int=10))
PRINCIPAL = ACCESS.actor_principal_id
PATH = f"/v1/projects/{PROJECT_ID.value}/access-groups"
BODY = {"name": "support", "displayName": "SupportKnowledge", "expectedAccessRevision": 7}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "group-original",
}


class MockAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return ACCESS


class MockGroups(
    AccessGroupCreator, AccessGroupReader, AccessGroupRelationshipChanger, AccessGroupDeleter
):
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.changed = True
        self.metadata = AccessGroupMetadataDTO(
            ORGANIZATION_ID,
            PROJECT_ID,
            GROUP,
            ResourceName("support"),
            "SupportKnowledge",
            SAVED_RESULT.expires_at,
            8,
        )
        self.context: IdempotencyContextDTO | None = None
        self.request_id: RequestId | None = None

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateAccessGroupCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupCreationResultDTO:
        self.calls.append(command)
        self.context = context
        return AccessGroupCreationResultDTO(
            CreatedAccessGroupDTO(
                SAVED_RESULT.operation_id,
                ORGANIZATION_ID,
                PROJECT_ID,
                GROUP,
                PRINCIPAL,
                command.name,
                command.display_name.value,
                8,
            ),
            SAVED_RESULT,
        )

    @override
    async def inspect(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupMetadataDTO:
        self.calls.append(selector)
        return self.metadata

    @override
    async def list_principals(
        self, *, access: AccessContextDTO, query: ListAccessGroupPrincipalsQuery
    ) -> AccessGroupPrincipalsPageDTO:
        self.calls.append(query)
        return AccessGroupPrincipalsPageDTO(PROJECT_ID, GROUP, 8, (), None)

    @override
    async def change(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeAccessGroupRelationshipCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupRelationshipResultDTO:
        self.calls.append(command)
        self.context = context
        return AccessGroupRelationshipResultDTO(
            ORGANIZATION_ID,
            PROJECT_ID,
            GROUP,
            PRINCIPAL,
            command.principal_id,
            command.change_kind,
            8 if self.changed else 7,
            self.changed,
            AccessGroupRelationships(True, True),
            command.change_kind.success_status(changed=self.changed),
            SAVED_RESULT,
        )

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteAccessGroupCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> AccessGroupDeletionResultDTO:
        self.calls.append(command)
        self.context, self.request_id = context, request_id
        return AccessGroupDeletionResultDTO(
            DeletedAccessGroupDTO(
                SAVED_RESULT.operation_id, ORGANIZATION_ID, PROJECT_ID, GROUP, PRINCIPAL, 8
            ),
            SAVED_RESULT,
        )


def client_for(groups: MockGroups) -> TestClient:
    @asynccontextmanager
    async def operations() -> AsyncGenerator[MockGroups]:
        yield groups

    auth = MockAuthenticator()
    authenticate = HumanSessionDependency(
        auth,
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
        access_token_authenticator=auth,
    )
    app = FastAPI()
    register_error_handlers(app)
    configure_problem_openapi(app)
    app.include_router(
        create_access_group_router(authenticate, operations, operations, operations, operations)
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_create_maps_exact_names_review_and_original_creator_receipt() -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        response = client.post(PATH, json=BODY, headers=HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert (
        body["accessGroupId"],
        body["creatorPrincipalId"],
        body["name"],
        body["displayName"],
        body["accessRevision"],
    ) == (str(GROUP.value), str(PRINCIPAL.value), "support", "SupportKnowledge", 8)
    assert groups.context is not None
    assert "initialGrants" not in body and groups.context.requested_route == PATH
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("collection,operation", [("members", "member"), ("managers", "manager")])
def test_put_preserves_original_changed_or_unchanged_status(
    collection: str, operation: str
) -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        route = f"{PATH}/{GROUP.value}/{collection}/{PRINCIPAL.value}"
        first = client.put(route, json={"expectedAccessRevision": 7}, headers=HEADERS)
        assert first.status_code == 201 and first.json()[operation] is True
        groups.changed = False
        replay = client.put(route, json={"expectedAccessRevision": 7}, headers=HEADERS)
        assert replay.status_code == 200 and replay.json()["changed"] is False
        removed = client.delete(route, params={"expectedAccessRevision": 7}, headers=HEADERS)
        assert removed.status_code == 200 and removed.json()["removed"] is True


def test_exact_metadata_empty_page_and_deletion_keep_scope_without_inventory() -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        for route in [f"{PATH}/{GROUP.value}", f"{PATH}/resolve?name=support"]:
            response = client.get(route, headers=HEADERS)
            assert response.status_code == 200 and response.json()["accessGroupId"] == str(
                GROUP.value
            )
        page = client.get(f"{PATH}/{GROUP.value}/members", headers=HEADERS)
        assert (
            page.status_code == 200
            and page.json()["items"] == []
            and page.json()["nextCursor"] is None
        )
        result = client.delete(f"{PATH}/{GROUP.value}?expectedAccessRevision=7", headers=HEADERS)
        assert (
            result.status_code == 200
            and result.json()["removed"] is True
            and groups.request_id is not None
        )
        assert client.get(PATH, headers=HEADERS).status_code == 405


@pytest.mark.parametrize(
    "body",
    [
        '{"name":"support","displayName":"Support","expectedAccessRevision":7,"expectedAccessRevision":8}',
        '{"name":"support","displayName":"Support","expectedAccessRevision":NaN}',
        "[]",
    ],
)
def test_ambiguous_or_non_object_json_is_rejected_before_execution(body: str) -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        response = client.post(
            PATH, content=body, headers={**HEADERS, "Content-Type": "application/json"}
        )
    assert response.status_code == 422 and not groups.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("revision", [True, 1.0, "7", -1, 9007199254740992])
def test_inexact_or_unsupported_body_review_is_rejected(revision: object) -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        response = client.post(
            PATH, json={**BODY, "expectedAccessRevision": revision}, headers=HEADERS
        )
    assert response.status_code == 422 and not groups.calls


@pytest.mark.parametrize(
    "suffix",
    [
        "?unknown=1",
        "?expectedAccessRevision=7&expectedAccessRevision=8",
        "?expectedAccessRevision=01",
        "?expectedAccessRevision=1.0",
    ],
)
def test_delete_query_is_exact_and_unambiguous(suffix: str) -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        response = client.delete(f"{PATH}/{GROUP.value}" + suffix, headers=HEADERS)
    assert response.status_code == 422 and not groups.calls


def test_get_body_delete_body_and_cookie_csrf_are_rejected() -> None:
    groups = MockGroups()
    with client_for(groups) as client:
        assert (
            client.request(
                "GET", f"{PATH}/{GROUP.value}", content="{}", headers=HEADERS
            ).status_code
            == 422
        )
        assert (
            client.request(
                "DELETE",
                f"{PATH}/{GROUP.value}?expectedAccessRevision=7",
                content="{}",
                headers=HEADERS,
            ).status_code
            == 422
        )
        assert (
            client.post(
                PATH,
                json=BODY,
                headers={k: v for k, v in HEADERS.items() if k != "X-Inframeld-CSRF"},
            ).status_code
            == 403
        )
    assert not groups.calls
