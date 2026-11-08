from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class IssueInvitationCommand(Command):
    """Validate local intent structure without treating reviewed state as authority.

    Current existence, parent scopes, action eligibility and exact affected Project
    coverage still require authoritative observations in the application workflow.
    """

    organization_id: OrganizationId
    assignments: tuple[InvitationAssignmentDTO, ...]
    expected_access_revision: int
    expected_project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...]
    expires_in_seconds: int | None = None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.expected_access_revision)
        if len(self.expected_project_access_revisions) > 100:
            raise ValueError("An invitation may review at most 100 Projects.")

        reviewed_projects: set[ProjectId] = set()
        for reviewed in self.expected_project_access_revisions:
            RevisionValidation.require(reviewed.access_revision)
            if reviewed.project_id in reviewed_projects:
                raise ValueError("An invitation must review each Project exactly once.")
            reviewed_projects.add(reviewed.project_id)

        if self.expires_in_seconds is not None:
            if type(self.expires_in_seconds) is not int:
                raise TypeError("An invitation lifetime requires whole seconds.")
            if self.expires_in_seconds <= 0:
                raise ValueError("An invitation lifetime must be positive.")

        self._validate_assignments()

    def _validate_assignments(self) -> None:
        if not 1 <= len(self.assignments) <= 100:
            raise ValueError("An invitation requires between 1 and 100 assignments.")

        grants: set[tuple[InvitationTargetDTO, ActionId]] = set()
        relationships: set[
            InvitationProjectMembershipIntentDTO
            | InvitationGroupMembershipIntentDTO
            | InvitationGroupManagerIntentDTO
        ] = set()
        for intent in self.assignments:
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                if len(self.assignments) != 1:
                    raise ValueError("Admission-only intent cannot contain other assignments.")
            elif isinstance(intent, InvitationActionGrantIntentDTO):
                if type(intent.can_grant) is not bool:
                    raise TypeError("An intended grant level must be a boolean.")
                identity = (intent.target, intent.action_id)
                if identity in grants:
                    raise ValueError("An invitation cannot repeat an exact action assignment.")
                grants.add(identity)
            else:
                if intent in relationships:
                    raise ValueError("An invitation cannot repeat a relationship assignment.")
                relationships.add(intent)
