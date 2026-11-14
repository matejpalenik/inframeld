from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class ModelConnectionDTO:
    project_id: ProjectId
    connection_id: ModelConnectionId
    name: ResourceName
    display_name: str
    access: ModelConnectionAccessDTO
    connection_access_revision: int
    credential_present: bool
    credential_revision: int
