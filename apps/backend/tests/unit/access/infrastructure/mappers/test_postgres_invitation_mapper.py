"""Keep exact typed intent in nonsecret JSONB without inventing target existence."""

import json
from uuid import UUID

import pytest

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
from inframeld_backend.access.application.dtos.invitation_source_target_dto import (
    InvitationSourceTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_invitation_mapper import (
    PostgresInvitationMapper,
)

PROJECT = ProjectId(UUID(int=2))
GROUP = AccessGroupId(UUID(int=3))


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (InvitationAdmissionOnlyIntentDTO(), {"kind": "admission-only"}),
        (
            InvitationProjectMembershipIntentDTO(project_id=PROJECT),
            {"kind": "project-membership", "projectId": str(PROJECT.value)},
        ),
        (
            InvitationGroupMembershipIntentDTO(project_id=PROJECT, access_group_id=GROUP),
            {
                "kind": "group-membership",
                "projectId": str(PROJECT.value),
                "accessGroupId": str(GROUP.value),
            },
        ),
        (
            InvitationGroupManagerIntentDTO(project_id=PROJECT, access_group_id=GROUP),
            {
                "kind": "group-manager",
                "projectId": str(PROJECT.value),
                "accessGroupId": str(GROUP.value),
            },
        ),
    ],
)
def test_relationship_intent_keeps_exact_kind_and_ids(
    intent: InvitationAssignmentDTO, expected: dict[str, object]
) -> None:
    payload = PostgresInvitationMapper.to_payload((intent,))

    assert payload == [expected]
    assert json.loads(json.dumps(payload)) == [expected]
    assert PostgresInvitationMapper.from_payload(payload) == (intent,)


@pytest.mark.parametrize("level", [False, True])
@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (
            OrganizationGrantTargetDTO(organization_id=OrganizationId(UUID(int=1))),
            {"kind": "organization", "organizationId": str(UUID(int=1))},
        ),
        (
            ProjectGrantTargetDTO(project_id=PROJECT),
            {"kind": "project", "projectId": str(PROJECT.value)},
        ),
        (
            AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
            {
                "kind": "access-group",
                "projectId": str(PROJECT.value),
                "accessGroupId": str(GROUP.value),
            },
        ),
        (
            ApplicationAccountGrantTargetDTO(
                project_id=PROJECT, application_principal_id=PrincipalId(UUID(int=4))
            ),
            {
                "kind": "application-account",
                "projectId": str(PROJECT.value),
                "applicationPrincipalId": str(UUID(int=4)),
            },
        ),
        (
            InvitationPipelineTargetDTO(pipeline_id=UUID(int=10)),
            {"kind": "pipeline", "pipelineId": str(UUID(int=10))},
        ),
        (
            InvitationDeploymentTargetDTO(deployment_id=UUID(int=11)),
            {"kind": "deployment", "deploymentId": str(UUID(int=11))},
        ),
        (
            InvitationCollectionTargetDTO(collection_id=UUID(int=12)),
            {"kind": "collection", "collectionId": str(UUID(int=12))},
        ),
        (
            InvitationSourceTargetDTO(source_id=UUID(int=13)),
            {"kind": "source", "sourceId": str(UUID(int=13))},
        ),
        (
            InvitationModelConnectionTargetDTO(model_connection_id=UUID(int=14)),
            {"kind": "model-connection", "modelConnectionId": str(UUID(int=14))},
        ),
        (
            InvitationProcessingProfileTargetDTO(processing_profile_id=UUID(int=15)),
            {"kind": "processing-profile", "processingProfileId": str(UUID(int=15))},
        ),
        (
            InvitationEmbeddingProfileTargetDTO(embedding_profile_id=UUID(int=16)),
            {"kind": "embedding-profile", "embeddingProfileId": str(UUID(int=16))},
        ),
    ],
)
def test_closed_target_handoff_and_grant_level_survive_json(
    target: InvitationTargetDTO, expected: dict[str, object], level: bool
) -> None:
    """Future-owner shapes are serialized, never accepted as actual targets by this mapper."""
    intent = InvitationActionGrantIntentDTO(
        target=target, action_id=ActionId("explicit-action"), can_grant=level
    )

    payload = PostgresInvitationMapper.to_payload((intent,))

    assert payload == [
        {
            "kind": "action-grant",
            "target": expected,
            "actionId": "explicit-action",
            "canGrant": level,
        }
    ]
    assert json.loads(json.dumps(payload)) == payload
    assert PostgresInvitationMapper.from_payload(payload) == (intent,)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-an-array",
        [],
        [{}],
        [{"kind": "unknown"}],
        [{"kind": "admission-only", "unexpected": True}],
        [{"kind": "project-membership"}],
        [{"kind": "project-membership", "projectId": 42}],
        [{"kind": "project-membership", "projectId": "invalid"}],
        [{"kind": "group-membership", "projectId": str(PROJECT.value), "accessGroupId": None}],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "project", "projectId": str(PROJECT.value)},
                "actionId": "create-access-groups",
                "canGrant": "false",
            }
        ],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "project", "projectId": str(PROJECT.value)},
                "actionId": "create-access-groups",
                "canGrant": 1,
            }
        ],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "project", "projectId": str(PROJECT.value)},
                "actionId": "create-access-groups",
                "canGrant": None,
            }
        ],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "invented", "projectId": str(PROJECT.value)},
                "actionId": "create-access-groups",
                "canGrant": False,
            }
        ],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "project", "projectId": str(PROJECT.value), "unexpected": True},
                "actionId": "create-access-groups",
                "canGrant": False,
            }
        ],
        [
            {
                "kind": "action-grant",
                "target": {"kind": "organization"},
                "actionId": "admit-users",
                "canGrant": False,
            }
        ],
        [{"kind": "admission-only"}] * 101,
    ],
)
def test_malformed_stored_shape_is_rejected_without_coercion(payload: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        PostgresInvitationMapper.from_payload(payload)


def test_activation_revisions_keep_exact_original_ids_values_and_order() -> None:
    revisions = (
        InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=7),
        InvitationProjectAccessRevisionDTO(project_id=ProjectId(UUID(int=1)), access_revision=9),
    )
    payload = PostgresInvitationMapper.to_project_revisions(revisions)
    assert payload == [
        {"projectId": str(PROJECT.value), "accessRevision": 7},
        {"projectId": str(UUID(int=1)), "accessRevision": 9},
    ]
    assert (
        PostgresInvitationMapper.from_project_revisions(json.loads(json.dumps(payload)))
        == revisions
    )
    assert PostgresInvitationMapper.to_project_revisions(()) == []
    assert PostgresInvitationMapper.from_project_revisions([]) == ()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [None],
        [{"projectId": "invalid", "accessRevision": 1}],
        [{"projectId": str(PROJECT.value), "accessRevision": True}],
        [{"projectId": str(PROJECT.value), "accessRevision": 1.5}],
        [{"projectId": str(PROJECT.value), "accessRevision": 0}],
        [{"projectId": str(PROJECT.value), "accessRevision": 9007199254740992}],
        [{"projectId": str(PROJECT.value), "accessRevision": 1, "extra": True}],
        [{"projectId": str(PROJECT.value), "accessRevision": 1}] * 2,
        [{"projectId": str(UUID(int=i)), "accessRevision": 1} for i in range(101)],
    ],
)
def test_activation_revision_decoder_rejects_malformed_or_reduced_original(payload: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        PostgresInvitationMapper.from_project_revisions(payload)
