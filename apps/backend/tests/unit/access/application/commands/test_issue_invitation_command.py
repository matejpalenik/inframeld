"""Validate immutable promised effects without claiming targets or authority exist."""

from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

ORGANIZATION = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
GROUP = AccessGroupId(UUID(int=3))
APPLICATION = PrincipalId(UUID(int=4))
MEMBERSHIP = InvitationProjectMembershipIntentDTO(project_id=PROJECT)
GROUP_MEMBER = InvitationGroupMembershipIntentDTO(project_id=PROJECT, access_group_id=GROUP)
GROUP_MANAGER = InvitationGroupManagerIntentDTO(project_id=PROJECT, access_group_id=GROUP)
ADMISSION = InvitationAdmissionOnlyIntentDTO()
GRANT = InvitationActionGrantIntentDTO(
    target=AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
    action_id=ActionId("add-documents"),
    can_grant=True,
)
REVIEW = InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=7)


def _command(
    assignments: tuple[InvitationAssignmentDTO, ...],
    *,
    reviews: tuple[InvitationProjectAccessRevisionDTO, ...] = (REVIEW,),
) -> IssueInvitationCommand:
    return IssueInvitationCommand(
        organization_id=ORGANIZATION,
        assignments=assignments,
        expected_access_revision=9,
        expected_project_access_revisions=reviews,
    )


def test_membership_management_and_grant_intent_stays_exactly_as_requested() -> None:
    assignments = (MEMBERSHIP, GROUP_MANAGER, GRANT)

    command = _command(assignments)

    assert command.assignments == assignments
    assert command.expected_project_access_revisions == (REVIEW,)
    assert command.expected_access_revision == 9


def test_admission_only_has_no_implicit_membership_or_grant() -> None:
    command = _command((ADMISSION,), reviews=())

    assert command.assignments == (ADMISSION,)
    assert command.expected_project_access_revisions == ()


@pytest.mark.parametrize(
    "target",
    [
        OrganizationGrantTargetDTO(organization_id=ORGANIZATION),
        ProjectGrantTargetDTO(project_id=PROJECT),
        AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
        ApplicationAccountGrantTargetDTO(project_id=PROJECT, application_principal_id=APPLICATION),
        InvitationPipelineTargetDTO(pipeline_id=UUID(int=10)),
        InvitationDeploymentTargetDTO(deployment_id=UUID(int=11)),
        InvitationCollectionTargetDTO(collection_id=UUID(int=12)),
        InvitationSourceTargetDTO(source_id=UUID(int=13)),
        InvitationModelConnectionTargetDTO(model_connection_id=UUID(int=14)),
        InvitationProcessingProfileTargetDTO(processing_profile_id=UUID(int=15)),
        InvitationEmbeddingProfileTargetDTO(embedding_profile_id=UUID(int=16)),
    ],
)
def test_receiving_owner_gets_the_exact_typed_grant_target(target: InvitationTargetDTO) -> None:
    """A closed handoff shape does not establish a real resource or valid catalogue action."""
    intent = replace(GRANT, target=target)

    assert _command((intent,)).assignments == (intent,)


@pytest.mark.parametrize("size", [0, 101])
def test_assignment_count_outside_one_through_100_is_rejected(size: int) -> None:
    assignments = tuple(
        InvitationProjectMembershipIntentDTO(project_id=ProjectId(UUID(int=index)))
        for index in range(size)
    )

    with pytest.raises(ValueError):
        _command(assignments)


def test_100_distinct_intents_are_not_silently_truncated() -> None:
    assignments = tuple(
        InvitationProjectMembershipIntentDTO(project_id=ProjectId(UUID(int=index)))
        for index in range(100)
    )

    assert _command(assignments).assignments == assignments


@pytest.mark.parametrize("intent", [MEMBERSHIP, GROUP_MEMBER, GROUP_MANAGER])
def test_duplicate_relationship_intent_is_rejected(intent: InvitationAssignmentDTO) -> None:
    with pytest.raises(ValueError):
        _command((intent, intent))


@pytest.mark.parametrize("second_level", [False, True])
def test_duplicate_grant_identity_is_rejected_even_with_a_different_level(
    second_level: bool,
) -> None:
    with pytest.raises(ValueError):
        _command((GRANT, replace(GRANT, can_grant=second_level)))


def test_admission_only_cannot_be_mixed_with_other_effects() -> None:
    with pytest.raises(ValueError):
        _command((ADMISSION, MEMBERSHIP))


def test_duplicate_project_reviews_cannot_hide_a_different_reviewed_revision() -> None:
    with pytest.raises(ValueError):
        _command((MEMBERSHIP,), reviews=(REVIEW, replace(REVIEW, access_revision=8)))


def test_project_review_count_is_bounded_to_100() -> None:
    reviews = tuple(
        InvitationProjectAccessRevisionDTO(project_id=ProjectId(UUID(int=index)), access_revision=0)
        for index in range(101)
    )

    with pytest.raises(ValueError):
        _command((MEMBERSHIP,), reviews=reviews)


def test_largest_safe_reviewed_revision_is_preserved() -> None:
    command = replace(
        _command(
            (MEMBERSHIP,), reviews=(replace(REVIEW, access_revision=RevisionValidation.MAX_VALUE),)
        ),
        expected_access_revision=RevisionValidation.MAX_VALUE,
    )

    assert command.expected_access_revision == RevisionValidation.MAX_VALUE
    assert (
        command.expected_project_access_revisions[0].access_revision == RevisionValidation.MAX_VALUE
    )


def test_explicit_positive_lifetime_is_preserved_for_configured_limit_checks() -> None:
    command = replace(_command((ADMISSION,), reviews=()), expires_in_seconds=3600)

    assert command.expires_in_seconds == 3600


@pytest.mark.parametrize("revision", [True, False, -1, RevisionValidation.MAX_VALUE + 1])
def test_organization_review_requires_a_safe_nonnegative_whole_number(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(_command((ADMISSION,), reviews=()), expected_access_revision=revision)


@pytest.mark.parametrize("revision", [True, False, -1, RevisionValidation.MAX_VALUE + 1])
def test_each_project_review_requires_a_safe_nonnegative_whole_number(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        _command((MEMBERSHIP,), reviews=(replace(REVIEW, access_revision=revision),))


@pytest.mark.parametrize("lifetime", [True, False, 0, -1])
def test_explicit_lifetime_requires_positive_whole_seconds(lifetime: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(_command((ADMISSION,), reviews=()), expires_in_seconds=lifetime)


@pytest.mark.parametrize("level", [0, 1])
def test_grant_level_does_not_coerce_integers_into_permission(level: int) -> None:
    with pytest.raises(TypeError):
        _command((replace(GRANT, can_grant=level),))
