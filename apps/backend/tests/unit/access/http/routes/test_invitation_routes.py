from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from tests.support.human_admission_scenarios import ACCESS
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_invitation_session_verifier import MockInvitationSessionVerifier
from tests.support.mock_invitations import INVITATION, ORG, PROOF, RECIPIENT, TOKEN, MockInvitations

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_collection_target_dto import (
    InvitationCollectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_deployment_target_dto import (
    InvitationDeploymentTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_embedding_profile_target_dto import (
    InvitationEmbeddingProfileTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_processing_profile_target_dto import (
    InvitationProcessingProfileTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.application.dtos.invitation_source_target_dto import (
    InvitationSourceTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.invitation_browser_dependency import (
    InvitationBrowserDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.routes.invitation_routes import create_invitation_router
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

ISSUE = {
    "organizationId": str(ORG.value),
    "assignments": [{"kind": "admission-only"}],
    "expectedAccessRevision": 7,
    "expectedProjectAccessRevisions": [],
}
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "invitation-key",
}
BODIES = {
    "": ISSUE,
    f"/{INVITATION.value}/revoke": {"expectedAccessRevision": 8},
    "/preview": {"invitationToken": TOKEN.value},
    "/activate": {"invitationToken": TOKEN.value},
}


class MockManagementAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return ACCESS


def client_for(
    service: MockInvitations, verifier: MockInvitationSessionVerifier | None = None
) -> TestClient:
    @asynccontextmanager
    async def open_service() -> AsyncGenerator[MockInvitations]:
        yield service

    auth = MockManagementAuthenticator()
    csrf = CSRFProtectionDependency((HttpUrl("https://account.test"),))
    provider = verifier if verifier is not None else MockInvitationSessionVerifier(PROOF)
    app = FastAPI()
    register_error_handlers(app)
    configure_problem_openapi(app)
    app.include_router(
        create_invitation_router(
            ProductAccessDependency(
                auth,
                csrf,
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(ACCESS),
            ),
            InvitationBrowserDependency(provider, csrf),
            InvitationBrowserDependency(provider, csrf, observe_password_completion=True),
            open_service,
            open_service,
            open_service,
            open_service,
        )
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("replay", [False, True])
def test_issue_returns_201_and_secret_only_on_first_delivery(replay: bool) -> None:
    service = MockInvitations(replay=replay)
    with client_for(service) as client:
        response = client.post("/v1/invitations", json=ISSUE, headers=HEADERS)
    assert response.status_code == 201
    expected = {
        "operationId": "invitation-original",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
        "invitationId": str(INVITATION.value),
        "organizationId": str(ORG.value),
        "assignments": [{"kind": "admission-only"}],
        "expiresAt": "2030-01-01T00:00:00Z",
        "accessRevision": 8,
        "secretAvailable": not replay,
    }
    if not replay:
        expected["invitationToken"] = TOKEN.value
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"
    call = service.calls[0]
    assert call[0:2] == ("issue", ACCESS)
    assert isinstance(call[2], IssueInvitationCommand)
    assert call[2].organization_id == ORG and call[2].expected_access_revision == 7
    assert isinstance(call[3], IdempotencyContextDTO)
    assert call[3].method is HttpMethod.POST and call[3].requested_route == "/v1/invitations"
    assert call[3].key.value == "invitation-key"


def test_preview_without_key_uses_cookie_proof_without_password_observation() -> None:
    service, verifier = MockInvitations(), MockInvitationSessionVerifier(PROOF)
    with client_for(service, verifier) as client:
        response = client.post(
            "/v1/invitations/preview",
            json=BODIES["/preview"],
            headers={k: v for k, v in HEADERS.items() if k != "Idempotency-Key"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "invitationId": str(INVITATION.value),
        "organizationId": str(ORG.value),
        "assignments": [{"kind": "admission-only"}],
        "expiresAt": "2030-01-01T00:00:00Z",
        "scopes": [
            {
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "displayName": "Example Organization",
            }
        ],
    }
    assert verifier.calls == [(BrowserSessionCredential("controlled-cookie"), False)]
    assert service.calls[0][0:2] == ("preview", PROOF)
    assert service.calls[0][2] == PreviewInvitationQuery(TOKEN)
    assert response.headers["cache-control"] == "no-store"


def test_activation_maps_optional_prepared_proof_and_original_namespace() -> None:
    service, verifier = MockInvitations(replay=True), MockInvitationSessionVerifier(PROOF)
    with client_for(service, verifier) as client:
        response = client.post(
            "/v1/invitations/activate", json=BODIES["/activate"], headers=HEADERS
        )
    assert response.status_code == 200
    assert response.json() == {
        "operationId": "invitation-original",
        "invitationId": str(INVITATION.value),
        "organizationId": str(ORG.value),
        "principalId": str(RECIPIENT.value),
        "organizationAccessRevision": 10,
        "projectAccessRevisions": [],
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
    }
    assert verifier.calls == [(BrowserSessionCredential("controlled-cookie"), True)]
    assert service.calls[0][0:2] == ("activate", PROOF)
    assert service.calls[0][2] == ActivateInvitationCommand(TOKEN)
    assert isinstance(service.calls[0][3], IdempotencyContextDTO)
    assert service.calls[0][3].requested_route == "/v1/invitations/activate"
    assert response.headers["cache-control"] == "no-store"


def test_revoke_returns_original_scope_without_undo_fields() -> None:
    service = MockInvitations(replay=True)
    path = f"/{INVITATION.value}/revoke"
    with client_for(service) as client:
        response = client.post("/v1/invitations" + path, json=BODIES[path], headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "operationId": "invitation-original",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
        "invitationId": str(INVITATION.value),
        "organizationId": str(ORG.value),
        "accessRevision": 9,
        "revoked": True,
    }
    assert service.calls[0][0:2] == ("revoke", ACCESS)
    assert service.calls[0][2] == RevokeInvitationCommand(INVITATION, 8)
    assert isinstance(service.calls[0][3], IdempotencyContextDTO)
    assert service.calls[0][3].requested_route == "/v1/invitations" + path
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", list(BODIES))
@pytest.mark.parametrize(
    "error,status",
    [
        (AccessDeniedError(), 403),
        (ResourceNotFoundError(), 404),
        (ConflictError(), 409),
        (DependencyUnavailableError(), 503),
    ],
)
def test_safe_workflow_errors_never_echo_secret_and_are_not_cached(
    path: str, error: ApplicationError, status: int
) -> None:
    service = MockInvitations()
    service.error = error
    with client_for(service) as client:
        response = client.post("/v1/invitations" + path, json=BODIES[path], headers=HEADERS)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert TOKEN.value not in response.text


@pytest.mark.parametrize("path", list(BODIES))
@pytest.mark.parametrize(
    "body,status",
    [
        (b'{"invitationToken":"private-token","invitationToken":"other"}', 422),
        (b'{"value":NaN}', 422),
        (b"[]", 422),
        (b"\xff", 422),
        (b'{"padding":"' + b"x" * 32768 + b'"}', 413),
    ],
    ids=["duplicate", "nonfinite", "array", "utf8", "oversize"],
)
def test_received_body_is_bounded_unambiguous_json_before_workflow(
    path: str, body: bytes, status: int
) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations" + path,
            content=body,
            headers={**HEADERS, "Content-Type": "application/json"},
        )
    assert response.status_code == status
    if status == 422:
        assert response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-token" not in response.text


@pytest.mark.parametrize("path", list(BODIES))
def test_unknown_query_is_rejected_without_workflow(path: str) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations" + path + "?invitationToken=private-token",
            json=BODIES[path],
            headers=HEADERS,
        )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-token" not in response.text


# These rows prove closed transport representations, including future typed handoff.
# A controlled workflow does not establish a receiving resource producer or authority.
@pytest.mark.parametrize(
    "wire,intent,reviews",
    [
        pytest.param(
            {"kind": "admission-only"}, InvitationAdmissionOnlyIntentDTO(), (), id="admission-only"
        ),
        pytest.param(
            {"kind": "project-membership", "projectId": str(UUID(int=17))},
            InvitationProjectMembershipIntentDTO(ProjectId(UUID(int=17))),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="project-membership",
        ),
        pytest.param(
            {
                "kind": "group-membership",
                "projectId": str(UUID(int=17)),
                "accessGroupId": str(UUID(int=29)),
            },
            InvitationGroupMembershipIntentDTO(
                ProjectId(UUID(int=17)), AccessGroupId(UUID(int=29))
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="group-membership",
        ),
        pytest.param(
            {
                "kind": "group-manager",
                "projectId": str(UUID(int=17)),
                "accessGroupId": str(UUID(int=29)),
            },
            InvitationGroupManagerIntentDTO(ProjectId(UUID(int=17)), AccessGroupId(UUID(int=29))),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="group-manager",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "create-projects",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                OrganizationGrantTargetDTO(ORG), ActionId("create-projects"), True
            ),
            (),
            id="organization-grant",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "project", "projectId": str(UUID(int=17))},
                "actionId": "create-access-groups",
                "canGrant": False,
            },
            InvitationActionGrantIntentDTO(
                ProjectGrantTargetDTO(ProjectId(UUID(int=17))),
                ActionId("create-access-groups"),
                False,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="project-grant",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {
                    "kind": "access-group",
                    "projectId": str(UUID(int=17)),
                    "accessGroupId": str(UUID(int=29)),
                },
                "actionId": "add-documents",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                AccessGroupGrantTargetDTO(ProjectId(UUID(int=17)), AccessGroupId(UUID(int=29))),
                ActionId("add-documents"),
                True,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="group-grant",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {
                    "kind": "application-account",
                    "projectId": str(UUID(int=17)),
                    "applicationPrincipalId": str(UUID(int=31)),
                },
                "actionId": "issue-application-keys",
                "canGrant": False,
            },
            InvitationActionGrantIntentDTO(
                ApplicationAccountGrantTargetDTO(
                    ProjectId(UUID(int=17)), PrincipalId(UUID(int=31))
                ),
                ActionId("issue-application-keys"),
                False,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="account-grant",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "pipeline", "pipelineId": str(UUID(int=50))},
                "actionId": "query",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                InvitationPipelineTargetDTO(UUID(int=50)), ActionId("query"), True
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="pipeline-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "deployment", "deploymentId": str(UUID(int=51))},
                "actionId": "query",
                "canGrant": False,
            },
            InvitationActionGrantIntentDTO(
                InvitationDeploymentTargetDTO(UUID(int=51)), ActionId("query"), False
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="deployment-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "collection", "collectionId": str(UUID(int=52))},
                "actionId": "view-collection",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                InvitationCollectionTargetDTO(UUID(int=52)), ActionId("view-collection"), True
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="collection-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "source", "sourceId": str(UUID(int=53))},
                "actionId": "view-source-configuration",
                "canGrant": False,
            },
            InvitationActionGrantIntentDTO(
                InvitationSourceTargetDTO(UUID(int=53)),
                ActionId("view-source-configuration"),
                False,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="source-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "model-connection", "modelConnectionId": str(UUID(int=54))},
                "actionId": "use-model-connection",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                InvitationModelConnectionTargetDTO(UUID(int=54)),
                ActionId("use-model-connection"),
                True,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="model-connection-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "processing-profile", "processingProfileId": str(UUID(int=55))},
                "actionId": "use-processing-profile",
                "canGrant": False,
            },
            InvitationActionGrantIntentDTO(
                InvitationProcessingProfileTargetDTO(UUID(int=55)),
                ActionId("use-processing-profile"),
                False,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="processing-profile-handoff",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "embedding-profile", "embeddingProfileId": str(UUID(int=56))},
                "actionId": "use-embedding-profile",
                "canGrant": True,
            },
            InvitationActionGrantIntentDTO(
                InvitationEmbeddingProfileTargetDTO(UUID(int=56)),
                ActionId("use-embedding-profile"),
                True,
            ),
            (InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 11),),
            id="embedding-profile-handoff",
        ),
    ],
)
@pytest.mark.parametrize("replay", [False, True])
def test_closed_intent_wire_maps_exact_inputs_and_saved_response(
    wire: dict[str, object],
    intent: InvitationAssignmentDTO,
    reviews: tuple[InvitationProjectAccessRevisionDTO, ...],
    replay: bool,
) -> None:
    service = MockInvitations(replay=replay)
    service.issued = replace(service.issued, assignments=(intent,))
    body = {
        **ISSUE,
        "assignments": [wire],
        "expectedProjectAccessRevisions": [
            {"projectId": str(item.project_id.value), "accessRevision": item.access_revision}
            for item in reviews
        ],
        "expiresInSeconds": 3600,
    }
    with client_for(service) as client:
        response = client.post("/v1/invitations", json=body, headers=HEADERS)
        if isinstance(intent, InvitationActionGrantIntentDTO):
            service.previewed = replace(
                service.previewed,
                assignments=(intent,),
                scopes=(InvitationScopeDTO(intent.target, "Stored target label"),),
            )
            preview = client.post(
                "/v1/invitations/preview", json=BODIES["/preview"], headers=HEADERS
            )
            assert preview.status_code == 200
            assert preview.json()["assignments"] == [wire]
            assert preview.json()["scopes"] == [
                {"target": wire["target"], "displayName": "Stored target label"}
            ]
    assert response.status_code == 201
    assert response.json()["assignments"] == [wire]
    assert response.json()["secretAvailable"] is (not replay)
    assert ("invitationToken" in response.json()) is (not replay)
    assert service.calls[0][2] == IssueInvitationCommand(ORG, (intent,), 7, reviews, 3600)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"expectedAccessRevision": True}, id="boolean-revision"),
        pytest.param({"expectedAccessRevision": 1.5}, id="fractional-revision"),
        pytest.param({"expectedAccessRevision": -1}, id="negative-revision"),
        pytest.param({"expectedAccessRevision": 9007199254740992}, id="unsafe-revision"),
        pytest.param({"expectedAccessRevision": "7"}, id="string-revision"),
        pytest.param({"expiresInSeconds": None}, id="null-lifetime"),
        pytest.param({"expiresInSeconds": True}, id="boolean-lifetime"),
        pytest.param({"expiresInSeconds": 1.5}, id="fractional-lifetime"),
        pytest.param({"expiresInSeconds": 0}, id="zero-lifetime"),
        pytest.param({"expiresInSeconds": -1}, id="negative-lifetime"),
        pytest.param({"expiresInSeconds": 2592001}, id="over-hard-cap-lifetime"),
        pytest.param({"expiresInSeconds": "60"}, id="string-lifetime"),
        pytest.param({"assignments": []}, id="empty-intent"),
        pytest.param(
            {"assignments": [{"kind": "admission-only"}] * 101}, id="too-many-assignments"
        ),
        pytest.param({"assignments": [{"kind": "future-open-kind"}]}, id="unknown-assignment-tag"),
        pytest.param({"assignments": [dict[str, object]()]}, id="missing-assignment-tag"),
        pytest.param(
            {"assignments": [{"kind": "admission-only", "projectId": str(UUID(int=17))}]},
            id="mismatched-assignment-fields",
        ),
        pytest.param({"assignments": [{"kind": "project-membership"}]}, id="missing-project-id"),
        pytest.param(
            {"assignments": [{"kind": "project-membership", "projectId": "not-a-uuid"}]},
            id="malformed-project-id",
        ),
        pytest.param(
            {"assignments": [{"kind": "group-membership", "projectId": str(UUID(int=17))}]},
            id="missing-group-id",
        ),
        pytest.param(
            {
                "assignments": [
                    {
                        "kind": "group-manager",
                        "projectId": str(UUID(int=17)),
                        "accessGroupId": str(UUID(int=29)),
                        "unknown": True,
                    }
                ]
            },
            id="unknown-group-field",
        ),
        pytest.param(
            {
                "assignments": [
                    {"kind": "admission-only"},
                    {"kind": "project-membership", "projectId": str(UUID(int=17))},
                ]
            },
            id="mixed-admission-only",
        ),
        pytest.param(
            {"assignments": [{"kind": "project-membership", "projectId": str(UUID(int=17))}] * 2},
            id="duplicate-relationship",
        ),
        pytest.param(
            {
                "assignments": [
                    {
                        "kind": "action-grant",
                        "target": {"kind": "organization", "organizationId": str(ORG.value)},
                        "actionId": "create-projects",
                        "canGrant": False,
                    },
                    {
                        "kind": "action-grant",
                        "target": {"kind": "organization", "organizationId": str(ORG.value)},
                        "actionId": "create-projects",
                        "canGrant": True,
                    },
                ]
            },
            id="duplicate-grant-levels",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": 1}
                ]
                * 2
            },
            id="duplicate-project-reviews",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": True}
                ]
            },
            id="boolean-project-revision",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": 1.5}
                ]
            },
            id="fractional-project-revision",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": -1}
                ]
            },
            id="negative-project-revision",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": 9007199254740992}
                ]
            },
            id="unsafe-project-revision",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=17)), "accessRevision": "1"}
                ]
            },
            id="string-project-revision",
        ),
        pytest.param(
            {
                "expectedProjectAccessRevisions": [
                    {"projectId": str(UUID(int=i + 100)), "accessRevision": 1} for i in range(101)
                ]
            },
            id="too-many-project-reviews",
        ),
        pytest.param({"unknown": "private-field"}, id="unknown-top-level-field"),
    ],
)
def test_invalid_issue_models_never_enter_workflow(changes: dict[str, object]) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post("/v1/invitations", json={**ISSUE, **changes}, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-field" not in response.text


@pytest.mark.parametrize(
    "assignment",
    [
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "unknown"},
                "actionId": "use",
                "canGrant": True,
            },
            id="unknown-target-tag",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"organizationId": str(ORG.value)},
                "actionId": "use",
                "canGrant": True,
            },
            id="missing-target-tag",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "projectId": str(UUID(int=17))},
                "actionId": "use",
                "canGrant": True,
            },
            id="mismatched-target-fields",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {
                    "kind": "project",
                    "projectId": str(UUID(int=17)),
                    "unknown": "private-field",
                },
                "actionId": "use",
                "canGrant": True,
            },
            id="unknown-target-field",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "application-account", "projectId": str(UUID(int=17))},
                "actionId": "use",
                "canGrant": True,
            },
            id="missing-account-id",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "use",
                "canGrant": 0,
            },
            id="numeric-grant-level",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "use",
                "canGrant": "true",
            },
            id="string-grant-level",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "use",
                "canGrant": None,
            },
            id="null-grant-level",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "use",
            },
            id="missing-grant-level",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "",
                "canGrant": True,
            },
            id="empty-action",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": " ",
                "canGrant": True,
            },
            id="blank-action",
        ),
        pytest.param(
            {
                "kind": "action-grant",
                "target": {"kind": "organization", "organizationId": str(ORG.value)},
                "actionId": "x" * 101,
                "canGrant": True,
            },
            id="long-action",
        ),
    ],
)
def test_invalid_nested_grant_never_enters_workflow(assignment: dict[str, object]) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations", json={**ISSUE, "assignments": [assignment]}, headers=HEADERS
        )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-field" not in response.text


@pytest.mark.parametrize("revision", [0, 9007199254740991])
@pytest.mark.parametrize("lifetime", [1, 2592000])
def test_whole_safe_boundaries_and_exact_ordered_reviews_reach_workflow(
    revision: int, lifetime: int
) -> None:
    service = MockInvitations()
    wire = {"kind": "project-membership", "projectId": str(UUID(int=17))}
    reviews = [
        {"projectId": str(UUID(int=17)), "accessRevision": revision},
        {"projectId": str(UUID(int=23)), "accessRevision": 11},
    ]
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations",
            json={
                **ISSUE,
                "assignments": [
                    wire,
                    {"kind": "project-membership", "projectId": str(UUID(int=23))},
                ],
                "expectedAccessRevision": revision,
                "expectedProjectAccessRevisions": reviews,
                "expiresInSeconds": lifetime,
            },
            headers=HEADERS,
        )
    assert response.status_code == 201
    assert service.calls[0][2] == IssueInvitationCommand(
        ORG,
        (
            InvitationProjectMembershipIntentDTO(ProjectId(UUID(int=17))),
            InvitationProjectMembershipIntentDTO(ProjectId(UUID(int=23))),
        ),
        revision,
        (
            InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), revision),
            InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=23)), 11),
        ),
        lifetime,
    )


def test_maximum_unique_assignment_and_review_counts_are_admitted_by_transport() -> None:
    service = MockInvitations()
    projects = [ProjectId(UUID(int=i + 100)) for i in range(100)]
    body = {
        **ISSUE,
        "assignments": [
            {"kind": "project-membership", "projectId": str(project.value)} for project in projects
        ],
        "expectedProjectAccessRevisions": [
            {"projectId": str(project.value), "accessRevision": 1} for project in projects
        ],
    }
    with client_for(service) as client:
        response = client.post("/v1/invitations", json=body, headers=HEADERS)
    assert response.status_code == 201
    assert service.calls[0][2] == IssueInvitationCommand(
        ORG,
        tuple(InvitationProjectMembershipIntentDTO(project) for project in projects),
        7,
        tuple(InvitationProjectAccessRevisionDTO(project, 1) for project in projects),
        None,
    )


@pytest.mark.parametrize("path", list(BODIES))
def test_non_json_content_is_415_without_workflow(path: str) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations" + path,
            content="private-field",
            headers={**HEADERS, "Content-Type": "text/plain"},
        )
    assert response.status_code == 415
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-field" not in response.text


@pytest.mark.parametrize("path", ["", f"/{INVITATION.value}/revoke", "/activate"])
def test_mutations_require_original_key_without_workflow(path: str) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations" + path,
            json=BODIES[path],
            headers={k: v for k, v in HEADERS.items() if k != "Idempotency-Key"},
        )
    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.parametrize("revision", [True, 1.5, -1, 9007199254740992, "8"])
def test_revocation_requires_its_own_strict_safe_revision(revision: object) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post(
            f"/v1/invitations/{INVITATION.value}/revoke",
            json={"expectedAccessRevision": revision},
            headers=HEADERS,
        )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []


@pytest.mark.parametrize("path", ["/preview", "/activate"])
@pytest.mark.parametrize(
    "body,status",
    [
        pytest.param({"invitationToken": "private-invalid-token"}, 404, id="invalid-token"),
        pytest.param({"invitationToken": "B" * 43}, 404, id="noncanonical-token"),
        pytest.param({"invitationToken": None}, 422, id="null-token"),
        pytest.param({"invitationToken": True}, 422, id="boolean-token"),
        pytest.param({"invitationToken": 123}, 422, id="numeric-token"),
        pytest.param(
            {"invitationToken": TOKEN.value, "unknown": "private-field"}, 422, id="unknown-field"
        ),
    ],
)
def test_recipient_token_validation_is_safe_without_workflow(
    path: str, body: dict[str, object], status: int
) -> None:
    service = MockInvitations()
    with client_for(service) as client:
        response = client.post("/v1/invitations" + path, json=body, headers=HEADERS)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == []
    assert "private-invalid-token" not in response.text
    assert "private-field" not in response.text
    assert TOKEN.value not in response.text


def test_activation_returns_exact_original_project_revisions_in_saved_order() -> None:
    service = MockInvitations(replay=True)
    service.activated = replace(
        service.activated,
        project_access_revisions=(
            InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=23)), 9007199254740991),
            InvitationProjectAccessRevisionDTO(ProjectId(UUID(int=17)), 0),
        ),
    )
    with client_for(service) as client:
        response = client.post(
            "/v1/invitations/activate", json=BODIES["/activate"], headers=HEADERS
        )
    assert response.status_code == 200
    assert response.json()["projectAccessRevisions"] == [
        {"projectId": str(UUID(int=23)), "accessRevision": 9007199254740991},
        {"projectId": str(UUID(int=17)), "accessRevision": 0},
    ]
