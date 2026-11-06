from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_action_grant_dto import (
    AccessGroupActionGrantDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class AccessGroupActionGrantsPageDTO:
    project_id: ProjectId
    group_id: AccessGroupId
    action_id: ActionId
    items: tuple[AccessGroupActionGrantDTO, ...]
    next_cursor: str | None
