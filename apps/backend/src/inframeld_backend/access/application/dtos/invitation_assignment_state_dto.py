from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationAssignmentStateDTO:
    """Pair one retained intent with actual native observations, without authorizing it.

    The application checks the closed pairing and exact identifiers immediately.
    An absent recipient and false prerequisite flags remain observations, never
    synthetic evidence that prospective admission or membership already happened.
    """

    intent: InvitationAssignmentDTO
    facts: (
        ProjectMembershipChangeFactsDTO
        | AccessGroupChangeFactsDTO
        | OrganizationGrantManagementFactsDTO
        | ProjectActionGrantManagementFactsDTO
        | AccessGroupGrantManagementFactsDTO
        | ApplicationAccountGrantManagementFactsDTO
    )
