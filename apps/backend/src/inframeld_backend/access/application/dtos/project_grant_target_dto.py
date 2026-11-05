from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectGrantTargetDTO:
    project_id: ProjectId
