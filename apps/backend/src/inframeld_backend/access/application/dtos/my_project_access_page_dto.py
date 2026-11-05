from dataclasses import dataclass

from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class MyProjectAccessPageDTO:
    project_id: ProjectId
    principal_id: PrincipalId
    access_revision: int
    grants: tuple[MyProjectAccessGrantDTO, ...]
    group_memberships: tuple[AccessGroupId, ...]
    group_managements: tuple[AccessGroupId, ...]
    next_cursor: str | None
