from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_grant_dto import ProjectActionGrantDTO
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectActionGrantsPageDTO:
    project_id: ProjectId
    action_id: ActionId
    items: tuple[ProjectActionGrantDTO, ...]
    next_cursor: str | None
