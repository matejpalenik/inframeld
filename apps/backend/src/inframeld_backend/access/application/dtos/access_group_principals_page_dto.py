from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_principal_dto import (
    AccessGroupPrincipalDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class AccessGroupPrincipalsPageDTO:
    project_id: ProjectId
    group_id: AccessGroupId
    access_revision: int
    items: tuple[AccessGroupPrincipalDTO, ...]
    next_cursor: str | None
