from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True)
class CreateModelConnectionCommand(Command):
    project_id: ProjectId
    name: ResourceName
    display_name: SubmittedDisplayName
    access: ModelConnectionAccessDTO
