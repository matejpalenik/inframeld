from typing import Annotated

from pydantic import Field

from inframeld_backend.access.http.requests.invitation_action_grant_request import (
    InvitationActionGrantRequest,
)
from inframeld_backend.access.http.requests.invitation_admission_only_request import (
    InvitationAdmissionOnlyRequest,
)
from inframeld_backend.access.http.requests.invitation_group_manager_request import (
    InvitationGroupManagerRequest,
)
from inframeld_backend.access.http.requests.invitation_group_membership_request import (
    InvitationGroupMembershipRequest,
)
from inframeld_backend.access.http.requests.invitation_project_membership_request import (
    InvitationProjectMembershipRequest,
)

type InvitationAssignmentRequest = Annotated[
    InvitationAdmissionOnlyRequest
    | InvitationProjectMembershipRequest
    | InvitationGroupMembershipRequest
    | InvitationGroupManagerRequest
    | InvitationActionGrantRequest,
    Field(discriminator="kind"),
]
