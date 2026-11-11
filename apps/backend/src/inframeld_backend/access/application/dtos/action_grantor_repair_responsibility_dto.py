from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.enums.repair_responsibility_kind import (
    RepairResponsibilityKind,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class ActionGrantorRepairResponsibilityDTO:
    target: (
        OrganizationGrantTargetDTO
        | ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO
    )
    action_id: ActionId
    kind: Literal[RepairResponsibilityKind.ACTION_GRANTOR] = field(
        default=RepairResponsibilityKind.ACTION_GRANTOR, init=False
    )

    def __post_init__(self) -> None:
        if isinstance(self.target, OrganizationGrantTargetDTO):
            supported = self.action_id.value in frozenset(OrganizationAction)
        elif isinstance(self.target, ProjectGrantTargetDTO):
            supported = self.action_id.value in frozenset(ProjectAction)
        elif isinstance(self.target, AccessGroupGrantTargetDTO):
            supported = self.action_id.value in frozenset(AccessGroupAction)
        else:
            supported = self.action_id.value in frozenset(ApplicationAccountAction)
        if not supported:
            raise ValueError("The action is not supported for this exact target.")
