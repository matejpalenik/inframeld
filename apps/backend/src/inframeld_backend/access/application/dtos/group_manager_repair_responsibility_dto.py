from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.access.application.enums.repair_responsibility_kind import (
    RepairResponsibilityKind,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class GroupManagerRepairResponsibilityDTO:
    project_id: ProjectId
    access_group_id: AccessGroupId
    kind: Literal[RepairResponsibilityKind.GROUP_MANAGER] = field(
        default=RepairResponsibilityKind.GROUP_MANAGER, init=False
    )
