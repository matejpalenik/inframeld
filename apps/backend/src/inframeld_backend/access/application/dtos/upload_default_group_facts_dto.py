from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class UploadDefaultGroupFactsDTO:
    """Observe a requested group's scoped existence and both management relationships."""

    group_id: AccessGroupId
    project_id: ProjectId | None
    is_member: bool
    is_manager: bool
