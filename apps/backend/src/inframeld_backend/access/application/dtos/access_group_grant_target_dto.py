from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class AccessGroupGrantTargetDTO:
    project_id: ProjectId
    access_group_id: AccessGroupId
