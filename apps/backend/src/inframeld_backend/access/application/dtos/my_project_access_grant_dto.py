from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class MyProjectAccessGrantDTO:
    """Describe an actual stored own assignment on a concrete existing target."""

    target: ProjectGrantTargetDTO | AccessGroupGrantTargetDTO | ApplicationAccountGrantTargetDTO
    action_id: ActionId
    can_grant: bool
