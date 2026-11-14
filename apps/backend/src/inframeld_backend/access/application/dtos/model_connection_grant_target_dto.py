from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ModelConnectionGrantTargetDTO:
    project_id: ProjectId
    model_connection_id: ModelConnectionId
