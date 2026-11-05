from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.application.enums.my_project_access_item_kind import (
    MyProjectAccessItemKind,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class MyProjectAccessRelationshipDTO:
    kind: Literal[MyProjectAccessItemKind.MEMBERSHIP, MyProjectAccessItemKind.MANAGEMENT]
    project_id: ProjectId
    access_group_id: AccessGroupId
